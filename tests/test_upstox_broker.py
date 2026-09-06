"""Covers the two things that make live order handling trustworthy: recording the price the
exchange actually gave us, and parking a stop that triggers on tick rather than on a poll.

Everything network-facing is stubbed — these assert our handling of Upstox's responses, not
Upstox itself.
"""

from __future__ import annotations

import pytest

from algosathi.broker import upstox_broker as ub
from algosathi.broker.upstox_broker import UpstoxBroker
from algosathi.core.enums import OrderType, Side
from algosathi.core.models import OrderRequest


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def no_sleeping(monkeypatch):
    monkeypatch.setattr(ub.time, "sleep", lambda _: None)


@pytest.fixture(autouse=True)
def stub_instrument_lookup(monkeypatch):
    monkeypatch.setattr(ub, "resolve_instrument_key", lambda *a, **k: "NSE_EQ|TEST")


def broker(**kwargs) -> UpstoxBroker:
    return UpstoxBroker(access_token="token", **kwargs)


def buy(quantity: int = 1) -> OrderRequest:
    return OrderRequest(symbol="INFY", side=Side.BUY, quantity=quantity)


def test_records_the_traded_price_not_zero(monkeypatch):
    """The place-order response never contains a price. Recording the order without reading
    the traded price back is how a bot ends up computing P&L from zeros."""
    monkeypatch.setattr(ub.requests, "post", lambda *a, **k: FakeResponse({"data": {"order_ids": ["OID1"]}}))
    monkeypatch.setattr(
        ub.requests,
        "get",
        lambda *a, **k: FakeResponse(
            {"data": {"status": "complete", "average_price": 1536.48, "filled_quantity": 1}}
        ),
    )

    fill = broker().place_order(buy())
    assert fill.price == 1536.48
    assert fill.order_id == "OID1"


def test_records_the_quantity_actually_filled(monkeypatch):
    """A partial fill must not be booked as though the whole order went through."""
    monkeypatch.setattr(ub.requests, "post", lambda *a, **k: FakeResponse({"data": {"order_ids": ["OID2"]}}))
    monkeypatch.setattr(
        ub.requests,
        "get",
        lambda *a, **k: FakeResponse(
            {"data": {"status": "complete", "average_price": 100.0, "filled_quantity": 7}}
        ),
    )

    fill = broker().place_order(buy(quantity=10))
    assert fill.quantity == 7


def test_refuses_to_record_a_fill_when_no_price_ever_arrives(monkeypatch):
    """Silently booking a zero would poison P&L, the daily-loss limit and the dashboard.
    Failing loudly leaves one order to reconcile by hand instead."""
    monkeypatch.setattr(ub.requests, "post", lambda *a, **k: FakeResponse({"data": {"order_ids": ["OID3"]}}))
    monkeypatch.setattr(
        ub.requests,
        "get",
        lambda *a, **k: FakeResponse({"data": {"status": "open", "filled_quantity": 0}}),
    )

    recorded = []
    with pytest.raises(RuntimeError, match="no traded price"):
        broker(trade_recorder=recorded.append).place_order(buy())
    assert recorded == []


def test_gives_up_immediately_on_a_rejected_order(monkeypatch):
    monkeypatch.setattr(ub.requests, "post", lambda *a, **k: FakeResponse({"data": {"order_ids": ["OID4"]}}))
    monkeypatch.setattr(
        ub.requests,
        "get",
        lambda *a, **k: FakeResponse(
            {"data": {"status": "rejected", "status_message": "insufficient funds"}}
        ),
    )

    with pytest.raises(RuntimeError, match="insufficient funds"):
        broker().place_order(buy())


def test_stop_order_carries_the_trigger_price():
    order = OrderRequest(
        symbol="INFY", side=Side.SELL, quantity=1, order_type=OrderType.SL_M, trigger_price=1500.0
    )
    body = broker()._order_body(order)

    assert body["order_type"] == "SL-M"  # Upstox's spelling
    assert body["trigger_price"] == 1500.0
    assert body["transaction_type"] == "SELL"


def test_market_order_sends_a_zero_trigger():
    """Upstox rejects a market order that carries a trigger price."""
    body = broker()._order_body(buy())
    assert body["order_type"] == "MARKET"
    assert body["trigger_price"] == 0


def test_resting_order_returns_an_id_without_waiting_for_a_fill(monkeypatch):
    """A parked stop has not filled — asking for its price would block until it timed out."""
    monkeypatch.setattr(ub.requests, "post", lambda *a, **k: FakeResponse({"data": {"order_ids": ["SL1"]}}))

    def explode(*a, **k):
        raise AssertionError("must not poll for a fill on a resting order")

    monkeypatch.setattr(ub.requests, "get", explode)

    order = OrderRequest(
        symbol="INFY", side=Side.SELL, quantity=1, order_type=OrderType.SL_M, trigger_price=1500.0
    )
    assert broker().place_resting_order(order) == "SL1"


def test_cancel_reports_whether_the_order_was_there(monkeypatch):
    monkeypatch.setattr(ub.requests, "delete", lambda *a, **k: FakeResponse({"data": {}}))
    assert broker().cancel_order("SL1") is True

    monkeypatch.setattr(ub.requests, "delete", lambda *a, **k: FakeResponse({}, status_code=404))
    assert broker().cancel_order("GONE") is False


def test_product_type_is_configurable():
    assert broker()._order_body(buy())["product"] == "D"
    assert broker(product="I")._order_body(buy())["product"] == "I"
