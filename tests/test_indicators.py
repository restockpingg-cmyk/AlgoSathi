import pandas as pd

from algosathi.strategy.indicators import ema, macd, rsi, sma


def test_sma_matches_manual_average():
    close = pd.Series([1, 2, 3, 4, 5], dtype=float)
    result = sma(close, 3)
    assert pd.isna(result.iloc[0])
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == 2.0  # mean(1,2,3)
    assert result.iloc[4] == 4.0  # mean(3,4,5)


def test_ema_reacts_faster_than_sma_after_a_jump():
    close = pd.Series([10.0] * 20 + [20.0] * 5)
    sma_result = sma(close, 10)
    ema_result = ema(close, 10)
    assert ema_result.iloc[-1] > sma_result.iloc[-1]


def test_rsi_is_high_after_a_sustained_uptrend():
    close = pd.Series(list(range(1, 30)), dtype=float)
    result = rsi(close, 14)
    assert result.iloc[-1] > 70


def test_rsi_is_low_after_a_sustained_downtrend():
    close = pd.Series(list(range(30, 1, -1)), dtype=float)
    result = rsi(close, 14)
    assert result.iloc[-1] < 30


def test_macd_line_is_positive_when_fast_ema_above_slow_ema():
    close = pd.Series(list(range(1, 60)), dtype=float)  # steady uptrend
    line, signal, hist = macd(close, fast_period=5, slow_period=10, signal_period=3)
    assert line.iloc[-1] > 0
    assert hist.iloc[-1] == line.iloc[-1] - signal.iloc[-1]
