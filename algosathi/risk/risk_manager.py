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

    def __init__(self, order_quantity: int, max_daily_loss: float, max_open_positions: int):
        self.order_quantity = order_quantity
        self.max_daily_loss = max_daily_loss
        self.max_open_positions = max_open_positions

    def evaluate(
        self,
        signal: Signal,
        position: Position,
        realized_pnl_today: float,
        open_position_count: int,
    ) -> OrderRequest | None:
        if signal.signal_type == SignalType.BUY:
            return self._evaluate_buy(signal, position, realized_pnl_today, open_position_count)
        if signal.signal_type == SignalType.EXIT:
            return self._evaluate_exit(signal, position)
        return None

    def _evaluate_buy(
        self,
        signal: Signal,
        position: Position,
        realized_pnl_today: float,
        open_position_count: int,
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

        return OrderRequest(symbol=signal.symbol, side=Side.BUY, quantity=self.order_quantity)

    def _evaluate_exit(self, signal: Signal, position: Position) -> OrderRequest | None:
        if position.is_flat:
            logger.debug(f"{signal.symbol}: EXIT signal ignored, no open position")
            return None
        return OrderRequest(symbol=signal.symbol, side=Side.SELL, quantity=position.quantity)
