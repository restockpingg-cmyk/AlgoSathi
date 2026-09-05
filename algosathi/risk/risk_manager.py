from __future__ import annotations

from loguru import logger

from algosathi.core.enums import Side, SignalType
from algosathi.core.models import OrderRequest, Position, Signal


class RiskManager:
    """Decides whether/how to act on a strategy Signal, given current position and account
    state. Sits between strategy output and broker.place_order — the strategy never talks to
    the broker directly.

    Exits are always allowed through (closing a position reduces risk); only new entries are
    gated by the daily-loss and max-open-position limits.
    """

    def __init__(
        self,
        order_quantity: int,
        max_daily_loss: float,
        max_open_positions: int,
        capital_per_trade: float | None = None,
        lot_size: int = 1,
    ):
        self.order_quantity = order_quantity
        self.max_daily_loss = max_daily_loss
        self.max_open_positions = max_open_positions
        self.capital_per_trade = capital_per_trade
        self.lot_size = max(1, lot_size)

    def size_for(self, price: float) -> int:
        """How many units to buy at `price`.

        With capital_per_trade set, the size scales with the instrument's price and is
        rounded down to a whole number of lots — one NIFTY lot is a very different amount of
        money from one share of INFY, and a fixed quantity silently ignores that.
        """
        if self.capital_per_trade is None:
            return self.order_quantity
        if price <= 0:
            return 0
        lots = int(self.capital_per_trade // (price * self.lot_size))
        return lots * self.lot_size

    def evaluate(
        self,
        signal: Signal,
        position: Position,
        realized_pnl_today: float,
        open_position_count: int,
        price: float | None = None,
    ) -> OrderRequest | None:
        if signal.signal_type == SignalType.BUY:
            return self._evaluate_buy(
                signal, position, realized_pnl_today, open_position_count, price
            )
        if signal.signal_type == SignalType.EXIT:
            return self._evaluate_exit(signal, position)
        return None

    def _evaluate_buy(
        self,
        signal: Signal,
        position: Position,
        realized_pnl_today: float,
        open_position_count: int,
        price: float | None = None,
    ) -> OrderRequest | None:
        if position.is_long:
            logger.debug(f"{signal.symbol}: BUY signal ignored, already long")
            return None

        if realized_pnl_today <= -abs(self.max_daily_loss):
            logger.warning(
                f"{signal.symbol}: BUY rejected, daily loss limit reached "
                f"(realized_pnl_today={realized_pnl_today:.2f})"
            )
            return None

        if not position.is_long and open_position_count >= self.max_open_positions:
            logger.warning(
                f"{signal.symbol}: BUY rejected, max_open_positions="
                f"{self.max_open_positions} reached"
            )
            return None

        quantity = self.size_for(price) if price is not None else self.order_quantity
        if quantity <= 0:
            logger.warning(
                f"{signal.symbol}: BUY rejected, capital_per_trade={self.capital_per_trade} "
                f"is not enough for one lot at {price}"
            )
            return None

        return OrderRequest(symbol=signal.symbol, side=Side.BUY, quantity=quantity)

    def _evaluate_exit(self, signal: Signal, position: Position) -> OrderRequest | None:
        if position.is_flat:
            logger.debug(f"{signal.symbol}: EXIT signal ignored, no open position")
            return None
        return OrderRequest(symbol=signal.symbol, side=Side.SELL, quantity=position.quantity)
