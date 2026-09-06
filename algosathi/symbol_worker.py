"""One symbol's slice of the live loop: its own strategy instance, its own stops, its own
resting stop order.

Scanning a universe is not the same as running N independent bots. The account-level limits —
max_open_positions, max_daily_loss, available capital — are shared, and a symbol that ignores
them puts on risk the other symbols have already accounted for. Those checks stay in
RiskManager and the day ledger, which every worker consults; a worker only owns the state
that is genuinely per-symbol.

A failure on one symbol must never stop the others being polled, so callers are expected to
run each `poll` inside its own try/except.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

import pandas as pd
from loguru import logger

from algosathi.broker.base import BrokerAdapter
from algosathi.broker.paper_broker import PaperBroker
from algosathi.core.enums import OrderType, Side, SignalType
from algosathi.core.models import Fill, OrderRequest, Signal
from algosathi.risk.position_guard import PositionGuard
from algosathi.risk.risk_manager import RiskManager
from algosathi.simulation import act_on_signal
from algosathi.strategy.base import Strategy


class SymbolWorker:
    def __init__(
        self,
        symbol: str,
        strategy: Strategy,
        guard: PositionGuard,
        broker: BrokerAdapter,
        risk_manager: RiskManager,
        quote: Callable[[], float | None] | None = None,
    ):
        self.symbol = symbol
        self.strategy = strategy
        self.guard = guard
        self.broker = broker
        self.risk_manager = risk_manager
        # Returns the last traded price right now. Used only when an order is actually going
        # out, so a wide universe does not spend a quote call per symbol per poll.
        self.quote = quote

        self.resting_stop_id: str | None = None
        self.last_price: float | None = None
        self.last_candle_at: datetime | None = None
        self.last_error: str | None = None
        self.acted = False

    # --- startup ------------------------------------------------------------

    def restore(self) -> None:
        """Re-arm stops for a position that survived a restart.

        Without this a bot that comes back mid-session holds a position with nothing watching
        it, and believes it is flat enough to buy the same symbol again.
        """
        position = self.broker.get_position(self.symbol)
        if position.quantity > 0:
            self.guard.on_entry(position.avg_price)
            logger.warning(
                f"{self.symbol}: resuming with {position.quantity} @ {position.avg_price:.2f} — "
                f"stops re-armed. Any stop order left resting at the broker by the previous run "
                f"is not tracked across restarts; check it by hand."
            )

    # --- per-poll -----------------------------------------------------------

    def _decide(self, candles: pd.DataFrame, now: datetime) -> Signal | None:
        """Stops first, strategy second — a stop must win over a strategy signal on the same
        candle, not race it."""
        last = candles.iloc[-1]

        if self.guard.is_armed:
            triggered = self.guard.check(
                float(last["close"]), now, low=float(last["low"]), high=float(last["high"])
            )
            if triggered is not None:
                logger.warning(f"{self.symbol}: {triggered.reason}")
                return Signal(
                    symbol=self.symbol,
                    signal_type=SignalType.EXIT,
                    reason=triggered.reason,
                    timestamp=last["timestamp"],
                )

        signal = self.strategy.on_candles(candles)
        if signal is not None and signal.signal_type is SignalType.BUY:
            allowed, why = self.guard.entry_allowed(now)
            if not allowed:
                logger.info(f"{self.symbol}: BUY skipped — {why}")
                return None
        return signal

    def poll(
        self,
        candles: pd.DataFrame,
        now: datetime,
        realized_pnl_today: float,
        entries_allowed: bool,
    ) -> Signal | None:
        """Runs one candle through this symbol. Returns the signal produced, if any, so the
        caller can log it centrally."""
        last_close = float(candles.iloc[-1]["close"])
        self.last_price = last_close
        self.last_candle_at = candles.iloc[-1]["timestamp"]

        if isinstance(self.broker, PaperBroker):
            self.broker.update_market_price(self.symbol, last_close)

        position = self.broker.get_position(self.symbol)

        # A stop resting at the exchange fires without telling us; the broker going flat while
        # the guard still holds a position is how we find out.
        if self.guard.is_armed and position.is_flat:
            logger.warning(f"{self.symbol}: closed at the broker — the resting stop fired")
            self.guard.on_exit()
            self.resting_stop_id = None

        # And the reverse: if an order was placed but recording its fill failed, the broker
        # holds a position the guard knows nothing about. Arm it rather than leave it naked.
        if position.quantity > 0 and not self.guard.is_armed:
            logger.warning(
                f"{self.symbol}: broker holds {position.quantity} @ {position.avg_price:.2f} "
                f"that this run did not open — arming stops on it"
            )
            self.guard.on_entry(position.avg_price)

        signal = self._decide(candles, now)
        if signal is None:
            return None

        if signal.signal_type is SignalType.BUY and not entries_allowed:
            logger.warning(f"{self.symbol}: BUY suppressed — trading is disabled from the dashboard")
            return signal

        # Fill at the price available *now*, not at the close of the candle that produced the
        # signal. That close is already a full candle plus a poll interval old, and filling
        # against it hands the paper account a price that is no longer on offer — which is
        # exactly the drift that made paper results diverge from the backtest. The backtest's
        # next-candle-open is the same idea expressed in bar terms: the first price obtainable
        # after the signal bar.
        fill_price = last_close
        if self.quote is not None:
            try:
                live_price = self.quote()
                if live_price:
                    fill_price = live_price
            except Exception as exc:  # noqa: BLE001 — a stale price beats skipping the trade
                logger.warning(
                    f"{self.symbol}: could not read the live price, filling at the last close "
                    f"{last_close:.2f} instead — {exc}"
                )

        if isinstance(self.broker, PaperBroker):
            self.broker.update_market_price(self.symbol, fill_price)

        fill = act_on_signal(
            signal, self.symbol, self.risk_manager, self.broker, realized_pnl_today, fill_price
        )
        self.acted = fill is not None
        if fill is not None:
            self._on_fill(fill)
        return signal

    def _on_fill(self, fill: Fill) -> None:
        if fill.side is Side.BUY:
            self.guard.on_entry(fill.price)
            self.resting_stop_id = self._park_stop(fill)
        else:
            self.guard.on_exit()
            # The strategy got out before the stop did, so the stop must be pulled: a live
            # stop order left behind would sell a position that no longer exists and open a
            # short.
            self._cancel_stop()

    def _park_stop(self, fill: Fill) -> str | None:
        """Places the fixed stop as a resting order at the exchange, where it triggers on tick
        rather than waiting for this bot's next poll — with 5-minute candles and a 60-second
        interval, a polled stop can be six minutes late."""
        stop_price = self.guard.resting_stop_price(fill.price)
        if stop_price is None:
            return None
        try:
            order_id = self.broker.place_resting_order(
                OrderRequest(
                    symbol=self.symbol,
                    side=Side.SELL,
                    quantity=fill.quantity,
                    order_type=OrderType.SL_M,
                    trigger_price=stop_price,
                )
            )
        except Exception as exc:  # noqa: BLE001 — a missing stop is loud, not fatal
            logger.error(f"{self.symbol}: could not park a stop at {stop_price} — {exc}")
            return None
        if order_id:
            logger.info(f"{self.symbol}: stop-loss order resting at {stop_price}")
        return order_id

    def _cancel_stop(self) -> None:
        if not self.resting_stop_id:
            return
        try:
            self.broker.cancel_order(self.resting_stop_id)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                f"{self.symbol}: could not cancel resting stop {self.resting_stop_id} — "
                f"cancel it manually before trading this symbol again: {exc}"
            )
        self.resting_stop_id = None

    def unrealized_pnl(self) -> float:
        position = self.broker.get_position(self.symbol)
        if not position.quantity or self.last_price is None:
            return 0.0
        return (self.last_price - position.avg_price) * position.quantity
