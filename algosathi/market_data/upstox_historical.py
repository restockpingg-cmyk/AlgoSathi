from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from algosathi.market_data.base import MarketDataProvider
from algosathi.market_data.instrument_lookup import resolve_instrument_key

BASE_URL = "https://api.upstox.com/v3/historical-candle"
INTRADAY_URL = f"{BASE_URL}/intraday"

CANDLE_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "open_interest"]


class UpstoxHistoricalProvider(MarketDataProvider):
    """Fetches historical OHLC candles from Upstox's v3 historical-candle REST API.

    See: https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/
    """

    def __init__(self, access_token: str, lookback_days: int = 5):
        self.access_token = access_token
        self.lookback_days = lookback_days

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _get(self, url: str) -> dict:
        response = requests.get(
            url,
            headers={"Accept": "application/json", "Authorization": f"Bearer {self.access_token}"},
            timeout=15,
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
