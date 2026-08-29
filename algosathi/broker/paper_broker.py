from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime

from algosathi.broker.base import BrokerAdapter
from algosathi.core.enums import Side
from algosathi.core.models import Fill, OrderRequest, Position

TradeRecorder = Callable[[Fill], None]


class PaperBroker(BrokerAdapter):
    """Simulated broker: no network calls, no real orders.

    Fills happen at whatever price was last pushed via `update_market_price` for that
    symbol — the runner is responsible for feeding that price (recommended: the *next*
    candle's open, to avoid look-ahead bias where a signal computed from a closed candle
    fills at that same candle's own close).

    Long-only in v1: selling more than the currently held quantity raises, since there is
    no short-selling support yet.
    """

    def __init__(self, starting_cash: float, trade_recorder: TradeRecorder | None = None):
        self._cash = starting_cash
        self._positions: dict[str, Position] = {}
        self._market_prices: dict[str, float] = {}
        self._trade_recorder = trade_recorder
        self.realized_pnl: float = 0.0

    def update_market_price(self, symbol: str, price: float) -> None:
        self._market_prices[symbol] = price

    def place_order(self, order: OrderRequest) -> Fill:
        price = self._market_prices.get(order.symbol)
        if price is None:
            raise RuntimeError(
                f"no market price known for {order.symbol}; call update_market_price() first"
            )

        position = self._positions.get(order.symbol, Position(order.symbol, 0, 0.0))

        if order.side == Side.BUY:
            new_quantity = position.quantity + order.quantity
            new_avg_price = (
                (position.avg_price * position.quantity) + (price * order.quantity)
            ) / new_quantity
            self._positions[order.symbol] = Position(order.symbol, new_quantity, new_avg_price)
            self._cash -= price * order.quantity
        else:  # SELL (close/reduce a long)
            if order.quantity > position.quantity:
                raise ValueError(
                    f"cannot sell {order.quantity} of {order.symbol}, only "
                    f"{position.quantity} held (shorting not supported in v1)"
                )
            self.realized_pnl += (price - position.avg_price) * order.quantity
            remaining = position.quantity - order.quantity
            avg_price = position.avg_price if remaining > 0 else 0.0
            self._positions[order.symbol] = Position(order.symbol, remaining, avg_price)
            self._cash += price * order.quantity

        fill = Fill(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=price,
            timestamp=datetime.now(),
            order_id=str(uuid.uuid4()),
        )
        if self._trade_recorder is not None:
            self._trade_recorder(fill)
        return fill

    def get_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if not p.is_flat]

    def get_position(self, symbol: str) -> Position:
        return self._positions.get(symbol, Position(symbol, 0, 0.0))

    def get_funds(self) -> float:
        return self._cash
