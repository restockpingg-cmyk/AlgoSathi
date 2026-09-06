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


def test_max_open_positions_is_shared_across_symbols():
    """A universe scan must not give each symbol its own budget — that would take on N times
    the risk the config asked for."""
    from algosathi.core.enums import SignalType
    from algosathi.core.models import Position, Signal

    manager = RiskManager(order_quantity=1, max_daily_loss=5000.0, max_open_positions=2)
    signal = Signal(
        symbol="TCS", signal_type=SignalType.BUY, reason="entry", timestamp=datetime(2026, 1, 1)
    )
    flat_in_tcs = Position(symbol="TCS", quantity=0, avg_price=0.0)

    # Two other symbols are already held, so this third entry must be refused even though
    # TCS itself is flat.
    assert manager.evaluate(signal, flat_in_tcs, 0.0, open_position_count=2) is None
    assert manager.evaluate(signal, flat_in_tcs, 0.0, open_position_count=1) is not None


def test_daily_loss_limit_blocks_every_symbol_not_just_the_loser():
    from algosathi.core.enums import SignalType
    from algosathi.core.models import Position, Signal

    manager = RiskManager(order_quantity=1, max_daily_loss=1000.0, max_open_positions=5)
    signal = Signal(
        symbol="WIPRO", signal_type=SignalType.BUY, reason="entry", timestamp=datetime(2026, 1, 1)
    )
    flat = Position(symbol="WIPRO", quantity=0, avg_price=0.0)

    assert manager.evaluate(signal, flat, -1000.0, open_position_count=0) is None
    assert manager.evaluate(signal, flat, -999.0, open_position_count=0) is not None
