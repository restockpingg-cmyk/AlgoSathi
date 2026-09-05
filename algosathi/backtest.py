from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from algosathi.analytics import equity_curve, summarize_by_symbol
from algosathi.broker.paper_broker import PaperBroker
from algosathi.config import RiskConfig
from algosathi.core.models import Fill
from algosathi.risk.risk_manager import RiskManager
from algosathi.simulation import simulate_candles
from algosathi.strategy.base import Strategy
from algosathi.strategy.rule_strategy import RuleStrategy


@dataclass
class BacktestResult:
    total_trades: int
    realized_pnl: float
    win_rate: float
    max_drawdown: float
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    trades: list[Fill] = field(default_factory=list)


def _max_drawdown(curve: pd.DataFrame) -> float:
    if curve.empty:
        return 0.0
    running_max = curve["cumulative_realized_pnl"].cummax()
    drawdown = curve["cumulative_realized_pnl"] - running_max
    return max(0.0, float(-drawdown.min()))


def _win_rate(trades: list[Fill]) -> float:
    """Fraction of SELL (closing) trades that realized a profit, using the same
    weighted-average-cost bookkeeping as analytics.py."""
    avg_price: dict[str, float] = {}
    position_qty: dict[str, int] = {}
    wins = 0
    sells = 0

    for trade in trades:
        symbol = trade.symbol
        qty = position_qty.get(symbol, 0)
        avg = avg_price.get(symbol, 0.0)

        if trade.side == "buy":
            new_qty = qty + trade.quantity
            avg_price[symbol] = (avg * qty + trade.price * trade.quantity) / new_qty
            position_qty[symbol] = new_qty
        else:
            sells += 1
            if (trade.price - avg) * trade.quantity > 0:
                wins += 1
            new_qty = qty - trade.quantity
            position_qty[symbol] = new_qty
            if new_qty == 0:
                avg_price[symbol] = 0.0

    return wins / sells if sells else 0.0


def run_strategy_backtest(
    strategy: Strategy,
    symbol: str,
    candles: pd.DataFrame,
    risk_config: RiskConfig,
    starting_cash: float = 100_000.0,
) -> BacktestResult:
    """Runs any Strategy through the exact same simulation loop the live bot uses
    (simulation.py), then computes performance metrics. Note: an open position at the end of
    the candle window is not marked-to-market — realized_pnl only reflects closed trades."""
    trades: list[Fill] = []
    risk_manager = RiskManager(
        order_quantity=risk_config.order_quantity,
        max_daily_loss=risk_config.max_daily_loss,
        max_open_positions=risk_config.max_open_positions,
    )
    broker = PaperBroker(starting_cash=starting_cash, trade_recorder=trades.append)

    simulate_candles(strategy, risk_manager, broker, symbol, candles)

    curve = equity_curve(trades)
    summary = summarize_by_symbol(trades)

    return BacktestResult(
        total_trades=len(trades),
        realized_pnl=float(summary["realized_pnl"].sum()) if not summary.empty else 0.0,
        win_rate=_win_rate(trades),
        max_drawdown=_max_drawdown(curve),
        equity_curve=curve.to_dict("records") if not curve.empty else [],
        trades=trades,
    )


def run_backtest(
    definition: dict[str, Any],
    symbol: str,
    candles: pd.DataFrame,
    risk_config: RiskConfig,
    starting_cash: float = 100_000.0,
) -> BacktestResult:
    """Backtests a rule-tree definition — the format the web builder produces."""
    return run_strategy_backtest(
        RuleStrategy(symbol=symbol, definition=definition),
        symbol,
        candles,
        risk_config,
        starting_cash,
    )
