from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import quote

import pandas as pd
import requests
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from algosathi.auth.upstox_auth import AuthRequiredError
from algosathi.market_data.base import MarketDataProvider
from algosathi.market_data.instrument_lookup import resolve_instrument_key

BASE_URL = "https://api.upstox.com/v3/historical-candle"
INTRADAY_URL = f"{BASE_URL}/intraday"
LTP_URL = "https://api.upstox.com/v3/market-quote/ltp"

CANDLE_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "open_interest"]


class UpstoxHistoricalProvider(MarketDataProvider):
    """Fetches historical OHLC candles from Upstox's v3 historical-candle REST API.

    See: https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/
    """

    def __init__(self, access_token: str, lookback_days: int = 5):
        self.access_token = access_token
        self.lookback_days = lookback_days

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_not_exception_type(AuthRequiredError),
    )
    def _get(self, url: str) -> dict:
        response = requests.get(
            url,
            headers={"Accept": "application/json", "Authorization": f"Bearer {self.access_token}"},
            timeout=15,
        )
        if response.status_code == 401:
            # Upstox can reject a token before the locally-cached expiry says it should — the
            # 3:30 AM IST rule is a floor, not a guarantee. Retrying a dead token just buries
            # the one actionable cause under a RetryError three attempts later.
            raise AuthRequiredError(
                "Upstox rejected the access token (401). Run "
                "`python -m algosathi.auth.cli_login` to get a fresh one."
            )
        response.raise_for_status()
        return response.json()

    def _fetch(self, instrument_key: str, interval_minutes: int, to_date: date, from_date: date) -> dict:
        return self._get(
            f"{BASE_URL}/{instrument_key}/minutes/{interval_minutes}/"
            f"{to_date.isoformat()}/{from_date.isoformat()}"
        )

    def _fetch_intraday(self, instrument_key: str, interval_minutes: int) -> dict:
        return self._get(f"{INTRADAY_URL}/{instrument_key}/minutes/{interval_minutes}")

    def get_ltp(self, symbol: str, exchange: str) -> float | None:
        """Last traded price right now, or None if the quote is unavailable.

        This is the price an order placed this instant would fill near. The last closed
        candle's close is already up to a full candle plus a poll interval old, so filling a
        paper order at it quietly awards a price that was not on offer any more.
        """
        exchange_code, _, segment = exchange.partition("_")
        instrument_key = resolve_instrument_key(
            self.access_token, symbol, exchange_code or exchange, segment or "EQ"
        )
        payload = self._get(f"{LTP_URL}?instrument_key={quote(instrument_key)}")
        data = payload.get("data") or {}
        if not data:
            return None

        # The response is keyed by "EXCHANGE:TRADINGSYMBOL" while the request uses
        # "EXCHANGE|token", so looking it up by the key we sent finds nothing. Match on the
        # instrument_token carried inside each entry, and fall back to the sole entry since we
        # only ever ask about one instrument.
        for entry in data.values():
            if entry.get("instrument_token") == instrument_key:
                return float(entry["last_price"])
        if len(data) == 1:
            only = next(iter(data.values()))
            return float(only["last_price"]) if "last_price" in only else None
        return None

    def get_recent_candles(
        self, symbol: str, exchange: str, interval_minutes: int, to_date: date | None = None
    ) -> pd.DataFrame:
        exchange_code, _, segment = exchange.partition("_")
        instrument_key = resolve_instrument_key(
            self.access_token, symbol, exchange_code or exchange, segment or "EQ"
        )

        backfilling = to_date is not None
        to_date = to_date or date.today()
        from_date = to_date - timedelta(days=self.lookback_days)

        rows = self._fetch(instrument_key, interval_minutes, to_date, from_date)
        candles = list(rows.get("data", {}).get("candles", []))

        # The historical endpoint only goes up to the previous trading day — today's candles
        # live on a separate intraday endpoint. Without this the live loop would poll all
        # session long and keep re-reading yesterday's close as though it were current.
        # Skipped when walking back through past windows, where "today" is irrelevant.
        if not backfilling:
            intraday = self._fetch_intraday(instrument_key, interval_minutes)
            candles += list(intraday.get("data", {}).get("candles", []))

        df = pd.DataFrame(candles, columns=CANDLE_COLUMNS)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        # The two endpoints can overlap on the boundary day; keep one row per timestamp.
        df = df.drop_duplicates(subset="timestamp", keep="last")
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df[["timestamp", "open", "high", "low", "close", "volume"]].astype(
            {"open": float, "high": float, "low": float, "close": float, "volume": int}
        )
