from __future__ import annotations

from collections import defaultdict

import pandas as pd

from algosathi.persistence.models import Trade


def summarize_by_symbol(trades: list[Trade]) -> pd.DataFrame:
    """Per-symbol realized P&L and open position, computed from the trade log using the same
    weighted-average-cost method as PaperBroker (so this always reconciles with it)."""
    position_qty: dict[str, int] = defaultdict(int)
    avg_price: dict[str, float] = defaultdict(float)
    realized_pnl: dict[str, float] = defaultdict(float)

    for trade in trades:
        symbol = trade.symbol
        if trade.side == "buy":
            new_qty = position_qty[symbol] + trade.quantity
            avg_price[symbol] = (
                avg_price[symbol] * position_qty[symbol] + trade.price * trade.quantity
            ) / new_qty
            position_qty[symbol] = new_qty
        else:  # sell
            realized_pnl[symbol] += (trade.price - avg_price[symbol]) * trade.quantity
            position_qty[symbol] -= trade.quantity
            if position_qty[symbol] == 0:
                avg_price[symbol] = 0.0

    symbols = sorted(set(position_qty) | set(realized_pnl))
    return pd.DataFrame(
        {
            "symbol": symbols,
            "realized_pnl": [realized_pnl[s] for s in symbols],
            "open_qty": [position_qty[s] for s in symbols],
            "avg_price": [avg_price[s] for s in symbols],
        }
    )


def equity_curve(trades: list[Trade]) -> pd.DataFrame:
    """Cumulative realized P&L over time, one point per SELL trade (BUYs don't realize P&L)."""
    avg_price: dict[str, float] = defaultdict(float)
    position_qty: dict[str, int] = defaultdict(int)

    points = []
    cumulative = 0.0
    for trade in trades:
        symbol = trade.symbol
        if trade.side == "buy":
            new_qty = position_qty[symbol] + trade.quantity
            avg_price[symbol] = (
                avg_price[symbol] * position_qty[symbol] + trade.price * trade.quantity
            ) / new_qty
            position_qty[symbol] = new_qty
        else:
            delta = (trade.price - avg_price[symbol]) * trade.quantity
            cumulative += delta
            position_qty[symbol] -= trade.quantity
            if position_qty[symbol] == 0:
                avg_price[symbol] = 0.0
            points.append({"timestamp": trade.timestamp, "cumulative_realized_pnl": cumulative})

    return pd.DataFrame(points)
