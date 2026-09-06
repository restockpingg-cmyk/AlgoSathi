from __future__ import annotations

import time
from datetime import datetime

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from algosathi.broker.base import BrokerAdapter
from algosathi.broker.paper_broker import TradeRecorder
from algosathi.core.enums import OrderType
from algosathi.core.models import Fill, OrderRequest, Position
from algosathi.market_data.instrument_lookup import resolve_instrument_key

# Order placement uses the dedicated low-latency host; positions/funds use the standard API host.
PLACE_ORDER_URL = "https://api-hft.upstox.com/v3/order/place"
CANCEL_ORDER_URL = "https://api-hft.upstox.com/v3/order/cancel"
ORDER_DETAILS_URL = "https://api.upstox.com/v2/order/details"
POSITIONS_URL = "https://api.upstox.com/v2/portfolio/short-term-positions"
FUNDS_URL = "https://api.upstox.com/v2/user/get-funds-and-margin"

# Upstox reports acceptance immediately but takes a moment to report the traded price, so a
# freshly-placed market order is polled briefly rather than read once.
FILL_POLL_ATTEMPTS = 10
FILL_POLL_DELAY_SECONDS = 0.5

# From the Upstox order-status appendix. "complete" is the only status meaning fully executed;
# the rest of the terminal set means the order is finished and will never fill further.
# Everything else ("open", "trigger pending", "validation pending", …) is still in flight.
COMPLETE = "complete"
TERMINAL_STATES = {COMPLETE, "cancelled", "rejected", "cancelled after market order"}


class UpstoxBroker(BrokerAdapter):
    """Real broker adapter backed by the Upstox v3 order API.

    See:
    https://upstox.com/developer/api-documentation/v3/place-order/
    https://upstox.com/developer/api-documentation/get-positions/
    https://upstox.com/developer/api-documentation/get-user-fund-margin/
    """

    def __init__(
        self,
        access_token: str,
        exchange: str = "NSE_EQ",
        trade_recorder: TradeRecorder | None = None,
        product: str = "D",
    ):
        self.access_token = access_token
        self.exchange = exchange
        self._trade_recorder = trade_recorder
        # "D" delivery, "I" intraday (MIS). Intraday positions are force-closed by the broker
        # near the close, so pair "I" with an exits.square_off_time rather than being
        # squared off at a price you did not choose.
        self.product = product

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

    def _instrument_key(self, symbol: str) -> str:
        exchange_code, _, segment = self.exchange.partition("_")
        return resolve_instrument_key(
            self.access_token, symbol, exchange_code or self.exchange, segment or "EQ"
        )

    def _order_body(self, order: OrderRequest) -> dict:
        # SL and SL_M carry a trigger; market and limit orders must send 0 or Upstox rejects
        # them. Upstox spells stop-loss-market as "SL-M".
        order_type = "SL-M" if order.order_type is OrderType.SL_M else order.order_type.value.upper()
        return {
            "quantity": order.quantity,
            "product": self.product,
            "validity": "DAY",
            "price": order.limit_price or 0,
            "instrument_token": self._instrument_key(order.symbol),
            "order_type": order_type,
            "transaction_type": order.side.value.upper(),
            "disclosed_quantity": 0,
            "trigger_price": order.trigger_price or 0,
            "is_amo": False,
        }

    def _submit(self, order: OrderRequest) -> str:
        """Places an order. Deliberately NOT retried.

        Placement is not idempotent: if the request reaches the exchange and only the response
        is lost, a retry places a second real order. Reads are retried freely elsewhere in this
        class; a write that creates a position gets exactly one attempt, and a failure is
        raised for a human to reconcile against the order book.
        """
        response = requests.post(
            PLACE_ORDER_URL, headers=self._headers(), json=self._order_body(order), timeout=15
        )
        response.raise_for_status()
        order_ids = response.json()["data"]["order_ids"]

        if not order_ids:
            raise RuntimeError("Upstox accepted the order but returned no order id")
        if len(order_ids) > 1:
            # Only sliced orders come back with several ids, and we never set slice=true.
            # Tracking one and forgetting the rest would leave real orders unmanaged, so
            # refuse rather than half-handle it.
            raise RuntimeError(
                f"Upstox returned {len(order_ids)} order ids ({', '.join(order_ids)}) for a "
                f"single order — every one of these is live and this code only tracks one. "
                f"Reconcile them by hand."
            )
        return order_ids[0]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_order(self, order_id: str) -> dict:
        response = requests.get(
            ORDER_DETAILS_URL, headers=self._headers(), params={"order_id": order_id}, timeout=15
        )
        response.raise_for_status()
        return response.json().get("data", {})

    def _await_fill_price(self, order_id: str) -> tuple[float, int]:
        """Polls the order until the exchange reports what actually traded.

        Upstox's place-order response confirms acceptance only — it never contains the price
        you got. Recording the order without this step is how a bot ends up with a P&L, a
        daily-loss limit, and a dashboard all computed from zeros.

        Waits for a terminal status rather than returning on the first non-zero fill: a market
        order can report a partial fill milliseconds before the rest lands, and booking the
        partial as the whole would leave the account holding more than the trade log says.
        """
        last_status = "unknown"
        for attempt in range(FILL_POLL_ATTEMPTS):
            data = self.get_order(order_id)
            last_status = str(data.get("status", "")).lower()
            filled = int(data.get("filled_quantity") or 0)
            price = float(data.get("average_price") or 0.0)

            if last_status == COMPLETE and filled and price:
                return price, filled

            if last_status in TERMINAL_STATES:
                # Cancelled or rejected. A partial fill before that is still a real position
                # and must be recorded; nothing filled is a clean failure.
                if filled and price:
                    logger.warning(
                        f"order {order_id} ended as {last_status!r} after partially filling "
                        f"{filled} @ {price:.2f} — recording the part that traded"
                    )
                    return price, filled
                raise RuntimeError(
                    f"order {order_id} ended as {last_status!r}: "
                    f"{data.get('status_message') or 'no reason given'}"
                )

            if attempt < FILL_POLL_ATTEMPTS - 1:
                time.sleep(FILL_POLL_DELAY_SECONDS)

        raise RuntimeError(
            f"order {order_id} was accepted but did not reach a terminal status within "
            f"{FILL_POLL_ATTEMPTS * FILL_POLL_DELAY_SECONDS:.1f}s (last status {last_status!r}). "
            f"Refusing to record a fill at an unknown price — this order may still be live at "
            f"the exchange, so reconcile it by hand before trading further."
        )

    def place_order(self, order: OrderRequest) -> Fill:
        order_id = self._submit(order)
        price, filled_quantity = self._await_fill_price(order_id)

        fill = Fill(
            symbol=order.symbol,
            side=order.side,
            quantity=filled_quantity,
            price=price,
            timestamp=datetime.now(),
            order_id=order_id,
        )
        if self._trade_recorder is not None:
            self._trade_recorder(fill)
        return fill

    def place_resting_order(self, order: OrderRequest) -> str | None:
        """Submits a stop order that waits at the exchange. Returns its order id — no Fill,
        because by definition it has not filled yet."""
        return self._submit(order)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def cancel_order(self, order_id: str) -> bool:
        response = requests.delete(
            CANCEL_ORDER_URL, headers=self._headers(), params={"order_id": order_id}, timeout=15
        )
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_positions(self) -> list[Position]:
        response = requests.get(POSITIONS_URL, headers=self._headers(), timeout=15)
        response.raise_for_status()
        data = response.json().get("data", [])
        return [
            Position(symbol=p["trading_symbol"], quantity=p["quantity"], avg_price=p["average_price"])
            for p in data
            if p["quantity"] != 0
        ]

    def get_position(self, symbol: str) -> Position:
        for position in self.get_positions():
            if position.symbol == symbol:
                return position
        return Position(symbol=symbol, quantity=0, avg_price=0.0)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_funds(self) -> float:
        response = requests.get(FUNDS_URL, headers=self._headers(), timeout=15)
        response.raise_for_status()
        return float(response.json()["data"]["equity"]["available_margin"])
