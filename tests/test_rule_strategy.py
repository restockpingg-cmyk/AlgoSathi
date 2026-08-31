from datetime import datetime, timedelta

import pandas as pd

from algosathi.core.enums import SignalType
from algosathi.strategy.rule_strategy import RuleStrategy


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


SMA_CROSSOVER_DEFINITION = {
    "entry": {
        "operator": "and",
        "conditions": [
            {
                "left": {"indicator": "sma", "period": 2},
                "op": "crosses_above",
                "right": {"indicator": "sma", "period": 4},
            }
        ],
    },
    "exit": {
        "operator": "and",
        "conditions": [
            {
                "left": {"indicator": "sma", "period": 2},
                "op": "crosses_below",
                "right": {"indicator": "sma", "period": 4},
            }
        ],
    },
}


def test_returns_none_without_enough_data():
    strategy = RuleStrategy(symbol="TEST", definition=SMA_CROSSOVER_DEFINITION)
    candles = make_candles([10, 9, 8])
    assert strategy.on_candles(candles) is None


def test_detects_bullish_then_bearish_crossover():
    strategy = RuleStrategy(symbol="TEST", definition=SMA_CROSSOVER_DEFINITION)

    downtrend = list(range(20, 9, -1))
    uptrend = list(range(10, 25))
    downtrend_again = list(range(24, 9, -1))
    closes = downtrend + uptrend + downtrend_again

    seen_signals = []
    for i in range(1, len(closes) + 1):
        signal = strategy.on_candles(make_candles(closes[:i]))
        if signal is not None:
            seen_signals.append(signal.signal_type)

    assert SignalType.BUY in seen_signals
    assert SignalType.EXIT in seen_signals
    assert seen_signals.index(SignalType.BUY) < seen_signals.index(SignalType.EXIT)


def test_constant_operand_and_multi_condition_and_group():
    definition = {
        "entry": {
            "operator": "and",
            "conditions": [
                {
                    "left": {"indicator": "sma", "period": 2},
                    "op": "crosses_above",
                    "right": {"indicator": "sma", "period": 4},
                },
                {"left": {"indicator": "close"}, "op": ">", "right": {"value": 1000}},
            ],
        },
        "exit": {"operator": "and", "conditions": [{"left": {"indicator": "close"}, "op": "<", "right": {"value": -1}}]},
    }
    strategy = RuleStrategy(symbol="TEST", definition=definition)

    # Same crossover shape as above, but close price never exceeds 1000, so the second
    # AND-ed condition should suppress the entry that would otherwise fire.
    downtrend = list(range(20, 9, -1))
    uptrend = list(range(10, 25))
    closes = downtrend + uptrend

    seen_signals = []
    for i in range(1, len(closes) + 1):
        signal = strategy.on_candles(make_candles(closes[:i]))
        if signal is not None:
            seen_signals.append(signal.signal_type)

    assert SignalType.BUY not in seen_signals


def test_or_group_fires_on_either_condition():
    definition = {
        "entry": {
            "operator": "or",
            "conditions": [
                {"left": {"indicator": "close"}, "op": ">", "right": {"value": 1_000_000}},
                {"left": {"indicator": "close"}, "op": ">", "right": {"value": 5}},
            ],
        },
        "exit": {"operator": "and", "conditions": [{"left": {"indicator": "close"}, "op": "<", "right": {"value": -1}}]},
    }
    strategy = RuleStrategy(symbol="TEST", definition=definition)
    signal = strategy.on_candles(make_candles([10, 10]))
    assert signal is not None
    assert signal.signal_type == SignalType.BUY
