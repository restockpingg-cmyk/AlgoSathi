"""The daily-loss circuit breaker is the last thing between a bad strategy and a bad day, so
its inputs get pinned down here."""

from datetime import date, datetime, timedelta
from itertools import count

import pytest

from algosathi.core.enums import Mode
from algosathi.persistence.db import get_session_factory, record_fill
from algosathi.core.enums import Side
from algosathi.core.models import Fill
from algosathi.risk.day_ledger import open_positions, realized_pnl_today

TODAY = date(2026, 3, 10)


@pytest.fixture
def session_factory(tmp_path):
    return get_session_factory(tmp_path / "test.db")


_order_ids = count()


def fill(symbol, side, quantity, price, when):
    # trades.order_id is unique, so every fill needs its own.
    return Fill(
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        timestamp=when,
        order_id=f"oid-{next(_order_ids)}",
    )


def at(hour, minute=0, day=TODAY):
    return datetime.combine(day, datetime.min.time()) + timedelta(hours=hour, minutes=minute)


def test_no_trades_means_no_loss(session_factory):
    assert realized_pnl_today(session_factory, Mode.PAPER, TODAY) == 0.0


def test_a_round_trip_realizes_its_profit(session_factory):
    record_fill(session_factory, fill("INFY", Side.BUY, 10, 100.0, at(10)), Mode.PAPER)
    record_fill(session_factory, fill("INFY", Side.SELL, 10, 110.0, at(11)), Mode.PAPER)
    assert realized_pnl_today(session_factory, Mode.PAPER, TODAY) == pytest.approx(100.0)


def test_losses_are_negative(session_factory):
    record_fill(session_factory, fill("INFY", Side.BUY, 10, 100.0, at(10)), Mode.PAPER)
    record_fill(session_factory, fill("INFY", Side.SELL, 10, 92.0, at(11)), Mode.PAPER)
    assert realized_pnl_today(session_factory, Mode.PAPER, TODAY) == pytest.approx(-80.0)


def test_an_open_position_is_not_counted_as_a_loss(session_factory):
    """Only closed trades are realized — an open position moving against you must not trip
    the daily limit on its own."""
    record_fill(session_factory, fill("INFY", Side.BUY, 10, 100.0, at(10)), Mode.PAPER)
    assert realized_pnl_today(session_factory, Mode.PAPER, TODAY) == 0.0


def test_yesterdays_losses_do_not_count_against_today(session_factory):
    yesterday = TODAY - timedelta(days=1)
    record_fill(session_factory, fill("INFY", Side.BUY, 10, 100.0, at(10, day=yesterday)), Mode.PAPER)
    record_fill(session_factory, fill("INFY", Side.SELL, 10, 50.0, at(11, day=yesterday)), Mode.PAPER)
    assert realized_pnl_today(session_factory, Mode.PAPER, TODAY) == 0.0


def test_paper_and_live_ledgers_are_separate(session_factory):
    """A paper loss must never trip the live circuit breaker, or vice versa."""
    record_fill(session_factory, fill("INFY", Side.BUY, 10, 100.0, at(10)), Mode.PAPER)
    record_fill(session_factory, fill("INFY", Side.SELL, 10, 50.0, at(11)), Mode.PAPER)
    assert realized_pnl_today(session_factory, Mode.LIVE, TODAY) == 0.0


def test_losses_accumulate_across_symbols(session_factory):
    record_fill(session_factory, fill("INFY", Side.BUY, 1, 100.0, at(10)), Mode.PAPER)
    record_fill(session_factory, fill("INFY", Side.SELL, 1, 90.0, at(11)), Mode.PAPER)
    record_fill(session_factory, fill("TCS", Side.BUY, 1, 200.0, at(12)), Mode.PAPER)
    record_fill(session_factory, fill("TCS", Side.SELL, 1, 180.0, at(13)), Mode.PAPER)
    assert realized_pnl_today(session_factory, Mode.PAPER, TODAY) == pytest.approx(-30.0)


def test_open_positions_survive_a_restart(session_factory):
    record_fill(session_factory, fill("INFY", Side.BUY, 5, 100.0, at(10)), Mode.PAPER)
    record_fill(session_factory, fill("TCS", Side.BUY, 3, 200.0, at(10)), Mode.PAPER)
    record_fill(session_factory, fill("TCS", Side.SELL, 3, 210.0, at(11)), Mode.PAPER)

    # INFY is still held; TCS was closed and must not look open.
    assert open_positions(session_factory, Mode.PAPER) == {"INFY": 5}
