import pytest

from algosathi.broker.paper_broker import PaperBroker
from algosathi.core.enums import Side
from algosathi.core.models import OrderRequest


def test_buy_updates_cash_and_position():
    broker = PaperBroker(starting_cash=10_000)
    broker.update_market_price("INFY", 100.0)

    fill = broker.place_order(OrderRequest(symbol="INFY", side=Side.BUY, quantity=10))

    assert fill.price == 100.0
    assert broker.get_funds() == 10_000 - 1_000
    position = broker.get_position("INFY")
    assert position.quantity == 10
    assert position.avg_price == 100.0


def test_buy_twice_averages_price():
    broker = PaperBroker(starting_cash=10_000)
    broker.update_market_price("INFY", 100.0)
    broker.place_order(OrderRequest(symbol="INFY", side=Side.BUY, quantity=10))

    broker.update_market_price("INFY", 120.0)
    broker.place_order(OrderRequest(symbol="INFY", side=Side.BUY, quantity=10))

    position = broker.get_position("INFY")
    assert position.quantity == 20
    assert position.avg_price == pytest.approx(110.0)


def test_sell_realizes_pnl_and_updates_cash():
    broker = PaperBroker(starting_cash=10_000)
    broker.update_market_price("INFY", 100.0)
    broker.place_order(OrderRequest(symbol="INFY", side=Side.BUY, quantity=10))

    broker.update_market_price("INFY", 130.0)
    fill = broker.place_order(OrderRequest(symbol="INFY", side=Side.SELL, quantity=10))

    assert fill.price == 130.0
    assert broker.realized_pnl == pytest.approx(300.0)  # (130 - 100) * 10
    assert broker.get_funds() == pytest.approx(10_000 - 1_000 + 1_300)
    assert broker.get_position("INFY").is_flat


def test_selling_more_than_held_raises():
    broker = PaperBroker(starting_cash=10_000)
    broker.update_market_price("INFY", 100.0)
    broker.place_order(OrderRequest(symbol="INFY", side=Side.BUY, quantity=5))

    with pytest.raises(ValueError):
        broker.place_order(OrderRequest(symbol="INFY", side=Side.SELL, quantity=10))


def test_place_order_without_known_price_raises():
    broker = PaperBroker(starting_cash=10_000)
    with pytest.raises(RuntimeError):
        broker.place_order(OrderRequest(symbol="INFY", side=Side.BUY, quantity=1))


def test_trade_recorder_is_called_on_fill():
    recorded = []
    broker = PaperBroker(starting_cash=10_000, trade_recorder=recorded.append)
    broker.update_market_price("INFY", 100.0)
    broker.place_order(OrderRequest(symbol="INFY", side=Side.BUY, quantity=1))

    assert len(recorded) == 1
    assert recorded[0].symbol == "INFY"


def test_get_positions_excludes_flat_positions():
    broker = PaperBroker(starting_cash=10_000)
    broker.update_market_price("INFY", 100.0)
    broker.place_order(OrderRequest(symbol="INFY", side=Side.BUY, quantity=5))
    broker.place_order(OrderRequest(symbol="INFY", side=Side.SELL, quantity=5))

    assert broker.get_positions() == []
