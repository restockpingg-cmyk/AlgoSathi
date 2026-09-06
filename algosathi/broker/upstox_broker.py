from __future__ import annotations

import time
from datetime import datetime

import requests
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
FILL_POLL_ATTEMPTS = 6
FILL_POLL_DELAY_SECONDS = 0.5

# Order states that mean "this will never fill", so polling should stop rather than run out
# the clock.
DEAD_ORDER_STATES = {"cancelled", "rejected"}


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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _submit(self, order: OrderRequest) -> str:
        response = requests.post(
            PLACE_ORDER_URL, headers=self._headers(), json=self._order_body(order), timeout=15
        )
        response.raise_for_status()
        return response.json()["data"]["order_ids"][0]

    def get_order(self, order_id: str) -> dict:
        response = requests.get(
            ORDER_DETAILS_URL, headers=self._headers(), params={"order_id": order_id}, timeout=15
        )
        response.raise_for_status()
        return response.json().get("data", {})

    def _await_fill_price(self, order_id: str) -> tuple[float, int]:
        """Polls the order until the exchange reports a traded price.

        Upstox's place-order response confirms acceptance only — it never contains the price
        you actually got. Recording the order without this step is how a bot ends up with a
        P&L, a daily-loss limit, and a dashboard all computed from zeros.
        """
        for attempt in range(FILL_POLL_ATTEMPTS):
            data = self.get_order(order_id)
            status = str(data.get("status", "")).lower()
            filled = int(data.get("filled_quantity") or 0)
            price = float(data.get("average_price") or 0.0)

            if filled and price:
                return price, filled
            if status in DEAD_ORDER_STATES:
                raise RuntimeError(
                    f"order {order_id} ended as {status!r}: "
                    f"{data.get('status_message') or 'no reason given'}"
                )
            if attempt < FILL_POLL_ATTEMPTS - 1:
                time.sleep(FILL_POLL_DELAY_SECONDS)

        raise RuntimeError(
            f"order {order_id} was accepted but no traded price appeared within "
            f"{FILL_POLL_ATTEMPTS * FILL_POLL_DELAY_SECONDS:.1f}s — refusing to record a fill "
            f"at an unknown price. Reconcile this order manually before trading further."
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

    def get_funds(self) -> float:
        response = requests.get(FUNDS_URL, headers=self._headers(), timeout=15)
        response.raise_for_status()
        return float(response.json()["data"]["equity"]["available_margin"])
