from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from algosathi.core.enums import OrderType, Side, SignalType


@dataclass(frozen=True)
class Candle:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class Signal:
    symbol: str
    signal_type: SignalType
    reason: str
    timestamp: datetime


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Side
    quantity: int
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    # Price at which a resting SL/SL_M order activates. Ignored for market/limit orders.
    trigger_price: float | None = None


@dataclass(frozen=True)
class Fill:
    symbol: str
    side: Side
    quantity: int
    price: float
    timestamp: datetime
    order_id: str
    # Brokerage, taxes and fees on this leg. Zero for live fills until the broker reports
    # them; the paper broker computes them so paper P&L is comparable to live P&L.
    charges: float = 0.0


@dataclass
class Position:
    symbol: str
    quantity: int
    avg_price: float

    @property
    def is_flat(self) -> bool:
        return self.quantity == 0

    @property
    def is_long(self) -> bool:
        return self.quantity > 0
