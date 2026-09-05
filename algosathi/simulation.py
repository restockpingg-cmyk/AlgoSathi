from __future__ import annotations

import pandas as pd
from loguru import logger

from algosathi.broker.base import BrokerAdapter
from algosathi.broker.paper_broker import PaperBroker
from algosathi.core.enums import Side, SignalType
from algosathi.core.models import Fill, Signal
from algosathi.risk.position_guard import PositionGuard
from algosathi.risk.risk_manager import RiskManager
from algosathi.strategy.base import Strategy


def act_on_signal(
    signal: Signal | None,
    strategy_symbol: str,
    risk_manager: RiskManager,
    broker: BrokerAdapter,
    realized_pnl_today: float,
    price: float | None = None,
) -> Fill | None:
    """Returns the Fill if the signal made it past the risk manager, else None — callers that
    log signals use this to record whether a signal was acted on or merely observed."""
    if signal is None:
        return None

    position = broker.get_position(strategy_symbol)
    open_position_count = len(broker.get_positions())

    order = risk_manager.evaluate(
        signal,
        position=position,
        realized_pnl_today=realized_pnl_today,
        open_position_count=open_position_count,
        price=price,
    )
    if order is None:
        return None

    fill = broker.place_order(order)
    logger.info(
        f"{fill.symbol}: {fill.side.value.upper()} {fill.quantity} @ {fill.price:.2f} "
        f"(signal: {signal.reason})"
    )
    return fill


def simulate_candles(
    strategy: Strategy,
    risk_manager: RiskManager,
    broker: PaperBroker,
    symbol: str,
    candles: pd.DataFrame,
    guard: PositionGuard | None = None,
) -> None:
    """Feed a historical OHLC DataFrame through the strategy/risk/broker pipeline one candle
    at a time, filling orders at the *next* candle's open to avoid look-ahead bias. Shared by
    the bot's CSV replay (runner.py) and the backtest engine (backtest.py).

    When a PositionGuard is supplied its stops are checked ahead of the strategy, so a stop
    loss always wins over a strategy signal on the same bar — and a backtest reflects the
    same exits the live bot would take.
    """
    for i in range(len(candles) - 1):
        history = candles.iloc[: i + 1]
        bar = candles.iloc[i]
        next_open = float(candles.iloc[i + 1]["open"])
        now = bar["timestamp"]

        signal = None
        if guard is not None and guard.is_armed:
            # Stops are measured against the bar that just closed, but fill at the next open
            # like every other order here — no peeking at the price we get filled at.
            triggered = guard.check(
                float(bar["close"]), now, low=float(bar["low"]), high=float(bar["high"])
            )
            if triggered is not None:
                signal = Signal(
                    symbol=symbol,
                    signal_type=SignalType.EXIT,
                    reason=triggered.reason,
                    timestamp=now,
                )

        if signal is None:
            signal = strategy.on_candles(history)
            if (
                signal is not None
                and signal.signal_type is SignalType.BUY
                and guard is not None
            ):
                allowed, why = guard.entry_allowed(now)
                if not allowed:
                    signal = None

        if signal is None:
            continue

        broker.update_market_price(symbol, next_open)
        fill = act_on_signal(signal, symbol, risk_manager, broker, broker.realized_pnl, next_open)
        if fill is not None and guard is not None:
            if fill.side == Side.BUY:
                guard.on_entry(fill.price)
            else:
                guard.on_exit()
