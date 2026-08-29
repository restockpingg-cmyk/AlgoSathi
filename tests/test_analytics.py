from datetime import datetime, timedelta

import pytest

from algosathi.analytics import equity_curve, summarize_by_symbol
from algosathi.persistence.models import Trade


def make_trade(symbol, side, quantity, price, minutes_offset) -> Trade:
    return Trade(
        order_id=f"{symbol}-{side}-{minutes_offset}",
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        timestamp=datetime(2026, 1, 1) + timedelta(minutes=minutes_offset),
        mode="paper",
    )


def test_summarize_by_symbol_matches_paper_broker_math():
    trades = [
        make_trade("INFY", "buy", 10, 100.0, 0),
        make_trade("INFY", "sell", 10, 130.0, 5),
    ]

    summary = summarize_by_symbol(trades)

    row = summary[summary["symbol"] == "INFY"].iloc[0]
    assert row["realized_pnl"] == pytest.approx(300.0)
    assert row["open_qty"] == 0


def test_summarize_by_symbol_averages_across_multiple_buys():
    trades = [
        make_trade("INFY", "buy", 10, 100.0, 0),
        make_trade("INFY", "buy", 10, 120.0, 1),
        make_trade("INFY", "sell", 5, 150.0, 2),
    ]

    summary = summarize_by_symbol(trades)
    row = summary[summary["symbol"] == "INFY"].iloc[0]

    assert row["open_qty"] == 15
    assert row["avg_price"] == pytest.approx(110.0)
    assert row["realized_pnl"] == pytest.approx((150.0 - 110.0) * 5)


def test_equity_curve_only_has_points_for_sells():
    trades = [
        make_trade("INFY", "buy", 10, 100.0, 0),
        make_trade("INFY", "sell", 10, 130.0, 5),
        make_trade("INFY", "buy", 5, 140.0, 6),
        make_trade("INFY", "sell", 5, 150.0, 7),
    ]

    curve = equity_curve(trades)

    assert len(curve) == 2
    assert curve["cumulative_realized_pnl"].iloc[0] == pytest.approx(300.0)
    assert curve["cumulative_realized_pnl"].iloc[1] == pytest.approx(300.0 + 50.0)
