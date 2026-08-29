from __future__ import annotations

from datetime import datetime

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from algosathi.broker.base import BrokerAdapter
from algosathi.broker.paper_broker import TradeRecorder
from algosathi.core.enums import Side
from algosathi.core.models import Fill, OrderRequest, Position
from algosathi.market_data.instrument_lookup import resolve_instrument_key

# Order placement uses the dedicated low-latency host; positions/funds use the standard API host.
PLACE_ORDER_URL = "https://api-hft.upstox.com/v3/order/place"
POSITIONS_URL = "https://api.upstox.com/v2/portfolio/short-term-positions"
FUNDS_URL = "https://api.upstox.com/v2/user/get-funds-and-margin"


class UpstoxBroker(BrokerAdapter):
    """Real broker adapter backed by the Upstox v3 order API.

    See:
    https://upstox.com/developer/api-documentation/v3/place-order/
    https://upstox.com/developer/api-documentation/get-positions/
    https://upstox.com/developer/api-documentation/get-user-fund-margin/
    """

    def __init__(self, access_token: str, exchange: str = "NSE_EQ", trade_recorder: TradeRecorder | None = None):
        self.access_token = access_token
        self.exchange = exchange
        self._trade_recorder = trade_recorder

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def place_order(self, order: OrderRequest) -> Fill:
        exchange_code, _, segment = self.exchange.partition("_")
        instrument_key = resolve_instrument_key(
            self.access_token, order.symbol, exchange_code or self.exchange, segment or "EQ"
        )

        body = {
            "quantity": order.quantity,
            "product": "D",  # delivery; change to "I" for intraday
            "validity": "DAY",
            "price": order.limit_price or 0,
            "instrument_token": instrument_key,
            "order_type": order.order_type.value.upper(),
            "transaction_type": order.side.value.upper(),
            "disclosed_quantity": 0,
            "trigger_price": 0,
            "is_amo": False,
        }
        response = requests.post(PLACE_ORDER_URL, headers=self._headers(), json=body, timeout=15)
        response.raise_for_status()
        order_ids = response.json()["data"]["order_ids"]

        # Upstox's place-order call only confirms acceptance, not the fill price. A production
        # setup should reconcile against the order-status/trade-book API for the actual fill
        # price; as a v1 placeholder we record the last known market price if the caller has one,
        # otherwise 0 — this is a known gap, flagged for follow-up before relying on it live.
        fill = Fill(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=order.limit_price or 0.0,
            timestamp=datetime.now(),
            order_id=order_ids[0],
        )
        if self._trade_recorder is not None:
            self._trade_recorder(fill)
        return fill

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
