"""A paper broker that fills at the quoted price for free shows a profit the same trades would
not have made live. These pin down that the two books stay separate and that the numbers
reconcile — gross minus everything paid must equal net, or the dashboard is lying."""

from __future__ import annotations

import pytest

from algosathi.broker.paper_broker import PaperBroker
from algosathi.charges import charges_for, slipped_price
from algosathi.config import ChargesConfig
from algosathi.core.enums import OrderType, Side
from algosathi.core.models import OrderRequest


def order(side: Side, quantity: int = 10) -> OrderRequest:
    return OrderRequest(symbol="INFY", side=side, quantity=quantity, order_type=OrderType.MARKET)


def free() -> ChargesConfig:
    return ChargesConfig(enabled=False)


def costly(**kwargs) -> ChargesConfig:
    defaults = dict(
        brokerage_flat=20.0,
        brokerage_pct=0.03,
        stt_pct_buy=0.1,
        stt_pct_sell=0.1,
        exchange_pct=0.00325,
        sebi_pct=0.0001,
        stamp_duty_pct_buy=0.015,
        gst_pct=18.0,
        slippage_pct=0.02,
    )
    defaults.update(kwargs)
    return ChargesConfig(**defaults)


def test_disabled_charges_reproduce_the_old_free_behaviour():
    broker = PaperBroker(starting_cash=100_000.0, charges_config=free())
    broker.update_market_price("INFY", 1000.0)
    broker.place_order(order(Side.BUY))
    broker.update_market_price("INFY", 1010.0)
    broker.place_order(order(Side.SELL))

    assert broker.realized_pnl == pytest.approx(100.0)
    assert broker.gross_realized_pnl == pytest.approx(100.0)
    assert broker.total_charges == 0.0


def test_slippage_works_against_you_on_both_legs():
    config = costly(slippage_pct=0.1)
    assert slipped_price(config, Side.BUY, 1000.0) == pytest.approx(1001.0)
    assert slipped_price(config, Side.SELL, 1000.0) == pytest.approx(999.0)


def test_gross_is_measured_at_quoted_prices_not_slipped_ones():
    """Gross must answer 'what if trading were free', so it cannot carry the slippage it is
    supposed to exclude."""
    broker = PaperBroker(starting_cash=100_000.0, charges_config=costly())
    broker.update_market_price("INFY", 1000.0)
    broker.place_order(order(Side.BUY))
    broker.update_market_price("INFY", 1010.0)
    broker.place_order(order(Side.SELL))

    assert broker.gross_realized_pnl == pytest.approx(100.0)


def test_net_is_worse_than_gross_and_the_two_reconcile():
    broker = PaperBroker(starting_cash=100_000.0, charges_config=costly())
    broker.update_market_price("INFY", 1000.0)
    broker.place_order(order(Side.BUY))
    broker.update_market_price("INFY", 1010.0)
    broker.place_order(order(Side.SELL))

    assert broker.realized_pnl < broker.gross_realized_pnl
    slippage_cost = broker.gross_realized_pnl - broker.realized_pnl - broker.total_charges
    assert slippage_cost > 0
    # 0.02% each way on ~1000 x 10 shares.
    assert slippage_cost == pytest.approx(4.0, abs=0.1)


def test_buy_side_charges_are_not_forgotten():
    """Counting only the sell leg understates costs by roughly half."""
    broker = PaperBroker(starting_cash=100_000.0, charges_config=costly())
    broker.update_market_price("INFY", 1000.0)
    broker.place_order(order(Side.BUY))

    # Nothing realized yet, but the buy's charges have already left the account.
    assert broker.total_charges > 0
    assert broker.realized_pnl == pytest.approx(-broker.total_charges)


def test_charges_come_out_of_cash():
    broker = PaperBroker(starting_cash=100_000.0, charges_config=costly())
    broker.update_market_price("INFY", 1000.0)
    broker.place_order(order(Side.BUY))

    spent = 100_000.0 - broker.get_funds()
    assert spent > 10_000.0  # more than the raw 10 x 1000 notional


def test_brokerage_takes_the_lower_of_flat_and_percentage():
    config = costly(brokerage_flat=20.0, brokerage_pct=0.03)
    # Small order: 0.03% of 10,000 = 3, below the 20 flat fee.
    small = charges_for(config, Side.BUY, 1000.0, 10)
    assert small.brokerage == pytest.approx(3.0)
    # Large order: 0.03% of 1,000,000 = 300, so the flat fee caps it.
    large = charges_for(config, Side.BUY, 1000.0, 1000)
    assert large.brokerage == pytest.approx(20.0)


def test_stamp_duty_is_charged_on_the_buy_leg_only():
    config = costly()
    assert charges_for(config, Side.BUY, 1000.0, 10).stamp_duty > 0
    assert charges_for(config, Side.SELL, 1000.0, 10).stamp_duty == 0.0


def test_gst_excludes_stt_and_stamp_duty():
    """GST applies to brokerage and exchange fees, not to the taxes."""
    config = costly(gst_pct=18.0)
    c = charges_for(config, Side.BUY, 1000.0, 10)
    assert c.gst == pytest.approx((c.brokerage + c.exchange + c.sebi) * 0.18)
