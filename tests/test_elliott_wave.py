from datetime import datetime, timedelta

import pandas as pd
import pytest

from algosathi.core.enums import SignalType
from algosathi.strategy.elliott_wave import ElliottWaveStrategy, find_pivots


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


def ramp(start: float, end: float, steps: int) -> list[float]:
    """A straight line from start to end, excluding start (so legs concatenate cleanly)."""
    step = (end - start) / steps
    return [start + step * (i + 1) for i in range(steps)]


def collect_signals(strategy, closes: list[float]) -> list[tuple[int, SignalType]]:
    signals = []
    for i in range(1, len(closes) + 1):
        signal = strategy.on_candles(make_candles(closes[:i]))
        if signal is not None:
            signals.append((i - 1, signal.signal_type))
    return signals


def test_invalid_parameters_raise():
    with pytest.raises(ValueError):
        ElliottWaveStrategy(symbol="TEST", zigzag_pct=0)
    with pytest.raises(ValueError):
        ElliottWaveStrategy(symbol="TEST", min_retracement=0.8, max_retracement=0.5)


def test_returns_none_without_enough_structure():
    strategy = ElliottWaveStrategy(symbol="TEST", zigzag_pct=5)
    assert strategy.on_candles(make_candles([100, 101, 102])) is None


def test_pivots_alternate_and_are_confirmed_after_the_extreme():
    closes = [100] + ramp(100, 120, 10) + ramp(120, 100, 10) + ramp(100, 125, 12)
    pivots = find_pivots(make_candles(closes), threshold_pct=5)

    assert [p.kind for p in pivots] == ["low", "high", "low"]
    # A pivot can only be called once price has reversed away from it.
    assert all(p.confirmed_at > p.index for p in pivots)
    assert pivots[1].price == pytest.approx(120)


def test_buys_the_break_above_the_wave_one_top():
    # Wave 1: 100 -> 120. Wave 2 retraces ~50% to 110. Wave 3 breaks out past 120.
    closes = [100] + ramp(100, 120, 10) + ramp(120, 110, 6) + ramp(110, 140, 20)
    strategy = ElliottWaveStrategy(symbol="TEST", zigzag_pct=5)

    signals = collect_signals(strategy, closes)
    kinds = [kind for _, kind in signals]

    assert SignalType.BUY in kinds
    buy_bar = next(bar for bar, kind in signals if kind is SignalType.BUY)
    # The entry is the first close strictly above the wave 1 top, not before it.
    assert closes[buy_bar] > 120
    assert closes[buy_bar - 1] <= 120


def test_no_entry_when_wave_two_retraces_all_of_wave_one():
    # Wave 2 undercuts wave 1's origin, which Elliott's hard rule forbids — no count, no trade.
    closes = [100] + ramp(100, 120, 10) + ramp(120, 95, 12) + ramp(95, 140, 25)
    strategy = ElliottWaveStrategy(symbol="TEST", zigzag_pct=5)

    kinds = [kind for _, kind in collect_signals(strategy, closes)]
    assert SignalType.BUY not in kinds


def test_no_entry_when_wave_two_barely_retraces():
    # A 10% retracement is well under the 38.2% floor, so this isn't a tradeable 1-2.
    closes = [100] + ramp(100, 120, 10) + ramp(120, 118, 4) + ramp(118, 140, 20)
    strategy = ElliottWaveStrategy(symbol="TEST", zigzag_pct=1, min_retracement=0.382)

    kinds = [kind for _, kind in collect_signals(strategy, closes)]
    assert SignalType.BUY not in kinds


def test_exits_at_the_fibonacci_wave_three_target():
    # Wave 1 = 20 points, wave 2 low = 110, so the 1.618 projection lands at 142.36.
    closes = [100] + ramp(100, 120, 10) + ramp(120, 110, 6) + ramp(110, 160, 30)
    strategy = ElliottWaveStrategy(symbol="TEST", zigzag_pct=5, target_extension=1.618)

    signals = collect_signals(strategy, closes)
    buy_bar = next(bar for bar, kind in signals if kind is SignalType.BUY)
    exit_bar = next(bar for bar, kind in signals if kind is SignalType.EXIT and bar > buy_bar)

    assert closes[exit_bar] >= 110 + 1.618 * 20
    assert closes[exit_bar - 1] < 110 + 1.618 * 20


def test_exits_when_a_swing_high_confirms():
    # Wave 3 tops out at 140 and rolls over before reaching the 1.618 target at 142.36.
    closes = [100] + ramp(100, 120, 10) + ramp(120, 110, 6) + ramp(110, 140, 20) + ramp(140, 115, 15)
    strategy = ElliottWaveStrategy(symbol="TEST", zigzag_pct=5)

    signals = collect_signals(strategy, closes)
    kinds = [kind for _, kind in signals]
    buy_bar = next(bar for bar, kind in signals if kind is SignalType.BUY)

    assert SignalType.EXIT in kinds
    assert any(kind is SignalType.EXIT and bar > buy_bar for bar, kind in signals)


def test_signals_do_not_depend_on_future_candles():
    """The whole point of the causal zig-zag: a decision made on bar i must be the same
    whether or not bars after i exist."""
    closes = [100] + ramp(100, 120, 10) + ramp(120, 110, 6) + ramp(110, 145, 22) + ramp(145, 120, 12)
    strategy = ElliottWaveStrategy(symbol="TEST", zigzag_pct=5)

    streamed = collect_signals(strategy, closes)
    for bar, kind in streamed:
        replayed = strategy.on_candles(make_candles(closes[: bar + 1]))
        assert replayed is not None and replayed.signal_type is kind
