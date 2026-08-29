from datetime import datetime

from algosathi.core.enums import Side, SignalType
from algosathi.core.models import Position, Signal
from algosathi.risk.risk_manager import RiskManager


def make_signal(signal_type: SignalType, symbol: str = "INFY") -> Signal:
    return Signal(symbol=symbol, signal_type=signal_type, reason="test", timestamp=datetime.now())


def test_buy_signal_while_flat_produces_order():
    risk = RiskManager(order_quantity=5, max_daily_loss=1000, max_open_positions=3)
    position = Position("INFY", 0, 0.0)

    order = risk.evaluate(make_signal(SignalType.BUY), position, realized_pnl_today=0, open_position_count=0)

    assert order is not None
    assert order.side == Side.BUY
    assert order.quantity == 5


def test_buy_signal_while_already_long_is_noop():
    risk = RiskManager(order_quantity=5, max_daily_loss=1000, max_open_positions=3)
    position = Position("INFY", 10, 100.0)

    order = risk.evaluate(make_signal(SignalType.BUY), position, realized_pnl_today=0, open_position_count=1)

    assert order is None


def test_buy_signal_rejected_when_daily_loss_limit_hit():
    risk = RiskManager(order_quantity=5, max_daily_loss=1000, max_open_positions=3)
    position = Position("INFY", 0, 0.0)

    order = risk.evaluate(
        make_signal(SignalType.BUY), position, realized_pnl_today=-1500, open_position_count=0
    )

    assert order is None


def test_buy_signal_rejected_when_max_open_positions_reached():
    risk = RiskManager(order_quantity=5, max_daily_loss=1000, max_open_positions=1)
    position = Position("INFY", 0, 0.0)

    order = risk.evaluate(
        make_signal(SignalType.BUY), position, realized_pnl_today=0, open_position_count=1
    )

    assert order is None


def test_exit_signal_while_long_produces_sell_for_full_quantity():
    risk = RiskManager(order_quantity=5, max_daily_loss=1000, max_open_positions=3)
    position = Position("INFY", 15, 100.0)

    order = risk.evaluate(make_signal(SignalType.EXIT), position, realized_pnl_today=0, open_position_count=1)

    assert order is not None
    assert order.side == Side.SELL
    assert order.quantity == 15


def test_exit_signal_while_flat_is_noop():
    risk = RiskManager(order_quantity=5, max_daily_loss=1000, max_open_positions=3)
    position = Position("INFY", 0, 0.0)

    order = risk.evaluate(make_signal(SignalType.EXIT), position, realized_pnl_today=0, open_position_count=0)

    assert order is None


def test_exit_allowed_even_when_daily_loss_limit_hit():
    risk = RiskManager(order_quantity=5, max_daily_loss=1000, max_open_positions=3)
    position = Position("INFY", 10, 100.0)

    order = risk.evaluate(
        make_signal(SignalType.EXIT), position, realized_pnl_today=-2000, open_position_count=1
    )

    assert order is not None
    assert order.side == Side.SELL
