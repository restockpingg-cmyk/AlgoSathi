from __future__ import annotations

import pandas as pd
from loguru import logger

from algosathi.broker.base import BrokerAdapter
from algosathi.broker.paper_broker import PaperBroker
from algosathi.core.models import Signal
from algosathi.risk.risk_manager import RiskManager
from algosathi.strategy.base import Strategy


def act_on_signal(
    signal: Signal | None,
    strategy_symbol: str,
    risk_manager: RiskManager,
    broker: BrokerAdapter,
    realized_pnl_today: float,
) -> None:
    if signal is None:
        return

    position = broker.get_position(strategy_symbol)
    open_position_count = len(broker.get_positions())

    order = risk_manager.evaluate(
        signal,
        position=position,
        realized_pnl_today=realized_pnl_today,
        open_position_count=open_position_count,
    )
    if order is None:
        return

    fill = broker.place_order(order)
    logger.info(
        f"{fill.symbol}: {fill.side.value.upper()} {fill.quantity} @ {fill.price:.2f} "
        f"(signal: {signal.reason})"
    )


def simulate_candles(
    strategy: Strategy,
    risk_manager: RiskManager,
    broker: PaperBroker,
    symbol: str,
    candles: pd.DataFrame,
) -> None:
    """Feed a historical OHLC DataFrame through the strategy/risk/broker pipeline one candle
    at a time, filling orders at the *next* candle's open to avoid look-ahead bias. Shared by
    the bot's CSV replay (runner.py) and the backtest engine (backtest.py)."""
    for i in range(len(candles) - 1):
        history = candles.iloc[: i + 1]
        signal = strategy.on_candles(history)
        if signal is not None:
            next_open = candles.iloc[i + 1]["open"]
            broker.update_market_price(symbol, float(next_open))
            act_on_signal(signal, symbol, risk_manager, broker, broker.realized_pnl)
