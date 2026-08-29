from datetime import datetime, timedelta

import pandas as pd
import pytest

from algosathi.core.enums import SignalType
from algosathi.strategy.sma_crossover import SmaCrossoverStrategy


def make_candles(closes: list[float]) -> pd.DataFrame:
    start = datetime(2026, 1, 1, 9, 15)
    return pd.DataFrame(
        {
            "timestamp": [start + timedelta(minutes=5 * i) for i in range(len(closes))],
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1000] * len(closes),
        }
    )


def test_invalid_periods_raise():
    with pytest.raises(ValueError):
        SmaCrossoverStrategy(symbol="TEST", fast_period=21, slow_period=9)


def test_returns_none_without_enough_data():
    strategy = SmaCrossoverStrategy(symbol="TEST", fast_period=2, slow_period=4)
    candles = make_candles([10, 9, 8])  # fewer than slow_period + 1
    assert strategy.on_candles(candles) is None


def test_detects_bullish_then_bearish_crossover():
    strategy = SmaCrossoverStrategy(symbol="TEST", fast_period=2, slow_period=4)

    # Downtrend, then a sustained uptrend (fast MA should cross above slow MA),
    # then a sustained downtrend again (fast MA should cross back below).
    downtrend = list(range(20, 9, -1))  # 20..10
    uptrend = list(range(10, 25))  # 10..24
    downtrend_again = list(range(24, 9, -1))  # 24..10
    closes = downtrend + uptrend + downtrend_again

    seen_signals = []
    for i in range(1, len(closes) + 1):
        candles = make_candles(closes[:i])
        signal = strategy.on_candles(candles)
        if signal is not None:
            seen_signals.append(signal.signal_type)

    assert SignalType.BUY in seen_signals
    assert SignalType.EXIT in seen_signals
    assert seen_signals.index(SignalType.BUY) < seen_signals.index(SignalType.EXIT)


def test_ema_mode_also_detects_crossover():
    strategy = SmaCrossoverStrategy(symbol="TEST", fast_period=2, slow_period=4, ma_type="ema")
    closes = list(range(20, 9, -1)) + list(range(10, 25))

    seen_signals = []
    for i in range(1, len(closes) + 1):
        signal = strategy.on_candles(make_candles(closes[:i]))
        if signal is not None:
            seen_signals.append(signal.signal_type)

    assert SignalType.BUY in seen_signals
