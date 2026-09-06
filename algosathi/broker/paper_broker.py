from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime

from algosathi.broker.base import BrokerAdapter
from algosathi.core.enums import Side
from algosathi.charges import charges_for, slipped_price
from algosathi.config import ChargesConfig
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

    def __init__(
        self,
        starting_cash: float,
        trade_recorder: TradeRecorder | None = None,
        charges_config: ChargesConfig | None = None,
    ):
        self._cash = starting_cash
        self._positions: dict[str, Position] = {}
        self._market_prices: dict[str, float] = {}
        self._trade_recorder = trade_recorder
        self._charges_config = charges_config

        # Two parallel books. The quoted one prices every fill at the price on screen, which
        # is what a naive paper broker reports; the real one prices fills where they actually
        # land and pays the bill. On a small edge these differ by more than the edge itself,
        # so reporting only one of them is how paper trading misleads.
        self._quoted_positions: dict[str, Position] = {}
        self.gross_realized_pnl: float = 0.0
        self._realized_at_fill_prices: float = 0.0
        self.total_charges: float = 0.0

    @property
    def realized_pnl(self) -> float:
        """What actually reaches the account: fills where they landed, minus every charge paid.

        Charges on a still-open position count too — that money has already left the account,
        and the daily-loss limit is about money gone, not money notionally at risk.
        """
        return self._realized_at_fill_prices - self.total_charges

    def update_market_price(self, symbol: str, price: float) -> None:
        self._market_prices[symbol] = price

    def place_order(self, order: OrderRequest) -> Fill:
        quoted = self._market_prices.get(order.symbol)
        if quoted is None:
            raise RuntimeError(
                f"no market price known for {order.symbol}; call update_market_price() first"
            )

        costs_on = self._charges_config is not None and self._charges_config.enabled
        price = slipped_price(self._charges_config, order.side, quoted) if costs_on else quoted
        charges = (
            charges_for(self._charges_config, order.side, price, order.quantity).total
            if costs_on
            else 0.0
        )
        self.total_charges += charges

        position = self._positions.get(order.symbol, Position(order.symbol, 0, 0.0))
        quoted_position = self._quoted_positions.get(order.symbol, Position(order.symbol, 0, 0.0))

        if order.side == Side.BUY:
            new_quantity = position.quantity + order.quantity
            self._positions[order.symbol] = Position(
                order.symbol,
                new_quantity,
                (position.avg_price * position.quantity + price * order.quantity) / new_quantity,
            )
            # The shadow book buys at the price on screen, so the gross figure is never
            # contaminated by the slippage it is meant to exclude.
            self._quoted_positions[order.symbol] = Position(
                order.symbol,
                new_quantity,
                (quoted_position.avg_price * quoted_position.quantity + quoted * order.quantity)
                / new_quantity,
            )
            self._cash -= price * order.quantity + charges
        else:  # SELL (close/reduce a long)
            if order.quantity > position.quantity:
                raise ValueError(
                    f"cannot sell {order.quantity} of {order.symbol}, only "
                    f"{position.quantity} held (shorting not supported in v1)"
                )
            self.gross_realized_pnl += (quoted - quoted_position.avg_price) * order.quantity
            self._realized_at_fill_prices += (price - position.avg_price) * order.quantity

            remaining = position.quantity - order.quantity
            self._positions[order.symbol] = Position(
                order.symbol, remaining, position.avg_price if remaining > 0 else 0.0
            )
            self._quoted_positions[order.symbol] = Position(
                order.symbol, remaining, quoted_position.avg_price if remaining > 0 else 0.0
            )
            self._cash += price * order.quantity - charges

        fill = Fill(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=price,
            timestamp=datetime.now(),
            order_id=str(uuid.uuid4()),
            charges=charges,
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
