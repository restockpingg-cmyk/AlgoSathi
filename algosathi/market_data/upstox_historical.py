from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from algosathi.market_data.base import MarketDataProvider
from algosathi.market_data.instrument_lookup import resolve_instrument_key

BASE_URL = "https://api.upstox.com/v3/historical-candle"

CANDLE_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "open_interest"]


class UpstoxHistoricalProvider(MarketDataProvider):
    """Fetches historical OHLC candles from Upstox's v3 historical-candle REST API.

    See: https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/
    """

    def __init__(self, access_token: str, lookback_days: int = 5):
        self.access_token = access_token
        self.lookback_days = lookback_days

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _fetch(self, instrument_key: str, interval_minutes: int, to_date: date, from_date: date) -> dict:
        url = (
            f"{BASE_URL}/{instrument_key}/minutes/{interval_minutes}/"
            f"{to_date.isoformat()}/{from_date.isoformat()}"
        )
        response = requests.get(
            url,
            headers={"Accept": "application/json", "Authorization": f"Bearer {self.access_token}"},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def get_recent_candles(
        self, symbol: str, exchange: str, interval_minutes: int, to_date: date | None = None
    ) -> pd.DataFrame:
        exchange_code, _, segment = exchange.partition("_")
        instrument_key = resolve_instrument_key(
            self.access_token, symbol, exchange_code or exchange, segment or "EQ"
        )

        to_date = to_date or date.today()
        from_date = to_date - timedelta(days=self.lookback_days)
        payload = self._fetch(instrument_key, interval_minutes, to_date, from_date)

        candles = payload.get("data", {}).get("candles", [])
        df = pd.DataFrame(candles, columns=CANDLE_COLUMNS)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df[["timestamp", "open", "high", "low", "close", "volume"]].astype(
            {"open": float, "high": float, "low": float, "close": float, "volume": int}
        )
