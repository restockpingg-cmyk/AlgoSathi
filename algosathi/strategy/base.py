from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from algosathi.core.models import Signal


class Strategy(ABC):
    """A strategy is a pure function of candle history to a trade signal.

    It does not know about positions, brokers, or risk limits — those are the
    runner's and RiskManager's job. This keeps strategies trivially unit-testable
    with plain DataFrames.
    """

    @abstractmethod
    def on_candles(self, candles: pd.DataFrame) -> Signal | None:
        """candles: OHLC DataFrame with columns [timestamp, open, high, low, close, volume],
        sorted ascending by timestamp, for a single instrument, containing only fully-closed
        candles. Returns a Signal or None if no action should be taken."""
        raise NotImplementedError
