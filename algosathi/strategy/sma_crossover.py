from __future__ import annotations

import pandas as pd

from algosathi.core.enums import SignalType
from algosathi.core.models import Signal
from algosathi.strategy.base import Strategy


class SmaCrossoverStrategy(Strategy):
    """Long-only fast/slow moving-average crossover.

    Emits BUY on a bullish crossover (fast MA moves from <= slow MA to > slow MA) and
    EXIT on a bearish crossover (fast MA moves from >= slow MA to < slow MA). Whether the
    signal should actually be acted on (e.g. ignore a BUY while already long) is decided
    downstream by the risk manager/runner, not here — this keeps the strategy a pure
    function of candle history, easy to unit-test in isolation.
    """

    def __init__(
        self,
        symbol: str,
        fast_period: int = 9,
        slow_period: int = 21,
        ma_type: str = "sma",
    ):
        if fast_period >= slow_period:
            raise ValueError("fast_period must be < slow_period")
        self.symbol = symbol
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.ma_type = ma_type

    def _moving_average(self, close: pd.Series, period: int) -> pd.Series:
        if self.ma_type == "ema":
            return close.ewm(span=period, adjust=False).mean()
        return close.rolling(window=period).mean()

    def on_candles(self, candles: pd.DataFrame) -> Signal | None:
        if len(candles) < self.slow_period + 1:
            return None

        close = candles["close"]
        fast_ma = self._moving_average(close, self.fast_period)
        slow_ma = self._moving_average(close, self.slow_period)

        prev_fast, curr_fast = fast_ma.iloc[-2], fast_ma.iloc[-1]
        prev_slow, curr_slow = slow_ma.iloc[-2], slow_ma.iloc[-1]

        if pd.isna(prev_fast) or pd.isna(prev_slow):
            return None

        last_timestamp = candles["timestamp"].iloc[-1]

        crossed_up = prev_fast <= prev_slow and curr_fast > curr_slow
        crossed_down = prev_fast >= prev_slow and curr_fast < curr_slow

        if crossed_up:
            return Signal(
                symbol=self.symbol,
                signal_type=SignalType.BUY,
                reason=f"fast SMA({self.fast_period}) crossed above slow SMA({self.slow_period})",
                timestamp=last_timestamp,
            )
        if crossed_down:
            return Signal(
                symbol=self.symbol,
                signal_type=SignalType.EXIT,
                reason=f"fast SMA({self.fast_period}) crossed below slow SMA({self.slow_period})",
                timestamp=last_timestamp,
            )
        return None
