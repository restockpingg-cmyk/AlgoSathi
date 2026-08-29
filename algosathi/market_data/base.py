from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class MarketDataProvider(ABC):
    """Source of OHLC candle history for a single instrument."""

    @abstractmethod
    def get_recent_candles(self, symbol: str, exchange: str, interval_minutes: int) -> pd.DataFrame:
        """Return a DataFrame of fully-closed candles (columns: timestamp, open, high, low,
        close, volume), sorted ascending, covering enough lookback for the strategy in use."""
        raise NotImplementedError
