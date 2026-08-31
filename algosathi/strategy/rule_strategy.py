from __future__ import annotations

from typing import Any

import pandas as pd

from algosathi.core.enums import SignalType
from algosathi.core.models import Signal
from algosathi.strategy import indicators as ind
from algosathi.strategy.base import Strategy

PRICE_FIELDS = {"open", "high", "low", "close"}
COMPARISON_OPS = {">", "<", ">=", "<="}
CROSS_OPS = {"crosses_above", "crosses_below"}


def _resolve_operand(operand: dict[str, Any], candles: pd.DataFrame) -> pd.Series:
    if "value" in operand:
        return pd.Series(float(operand["value"]), index=candles.index)

    indicator = operand["indicator"]
    source = candles[operand.get("source", "close")]

    if indicator in PRICE_FIELDS:
        return candles[indicator]
    if indicator == "sma":
        return ind.sma(source, operand["period"])
    if indicator == "ema":
        return ind.ema(source, operand["period"])
    if indicator == "rsi":
        return ind.rsi(source, operand.get("period", 14))
    if indicator in ("macd_line", "macd_signal", "macd_hist"):
        line, signal, hist = ind.macd(
            source,
            operand.get("fast_period", 12),
            operand.get("slow_period", 26),
            operand.get("signal_period", 9),
        )
        return {"macd_line": line, "macd_signal": signal, "macd_hist": hist}[indicator]
    raise ValueError(f"unknown indicator: {indicator}")


def _evaluate_condition(condition: dict[str, Any], candles: pd.DataFrame) -> pd.Series:
    left = _resolve_operand(condition["left"], candles)
    right = _resolve_operand(condition["right"], candles)
    op = condition["op"]

    if op == ">":
        return left > right
    if op == "<":
        return left < right
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    if op in CROSS_OPS:
        prev_left, prev_right = left.shift(1), right.shift(1)
        # Require two full consecutive valid readings on both sides before allowing a
        # crossover to fire — otherwise a NaN-vs-value comparison (always False) reads as
        # "was not above/below", producing a spurious crossover the instant an indicator's
        # warm-up period ends (e.g. the slower SMA in an SMA(2)/SMA(4) pair).
        valid = left.notna() & right.notna() & prev_left.notna() & prev_right.notna()
        if op == "crosses_above":
            raw = (left > right) & ~(prev_left > prev_right)
        else:
            raw = (left < right) & ~(prev_left < prev_right)
        return raw & valid
    raise ValueError(f"unknown operator: {op}")


def _evaluate_group(group: dict[str, Any], candles: pd.DataFrame) -> pd.Series:
    condition_series = [_evaluate_condition(c, candles) for c in group["conditions"]]
    combined = pd.concat(condition_series, axis=1).fillna(False)
    if group["operator"] == "and":
        return combined.all(axis=1)
    if group["operator"] == "or":
        return combined.any(axis=1)
    raise ValueError(f"unknown group operator: {group['operator']}")


class RuleStrategy(Strategy):
    """Long-only strategy driven by a JSON condition-tree definition (entry/exit), the
    engine behind the web strategy builder. See docs/plan for the definition schema — each
    side is a flat group of indicator/constant comparisons combined by a single and/or."""

    def __init__(self, symbol: str, definition: dict[str, Any]):
        self.symbol = symbol
        self.definition = definition

    def on_candles(self, candles: pd.DataFrame) -> Signal | None:
        if len(candles) < 2:
            return None

        last_timestamp = candles["timestamp"].iloc[-1]

        entry_series = _evaluate_group(self.definition["entry"], candles)
        if bool(entry_series.iloc[-1]):
            return Signal(
                symbol=self.symbol,
                signal_type=SignalType.BUY,
                reason="entry conditions met",
                timestamp=last_timestamp,
            )

        exit_series = _evaluate_group(self.definition["exit"], candles)
        if bool(exit_series.iloc[-1]):
            return Signal(
                symbol=self.symbol,
                signal_type=SignalType.EXIT,
                reason="exit conditions met",
                timestamp=last_timestamp,
            )

        return None
