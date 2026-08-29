from __future__ import annotations

from abc import ABC, abstractmethod

from algosathi.core.models import Fill, OrderRequest, Position


class BrokerAdapter(ABC):
    """Common interface for paper and live brokers. Strategy, risk, and runner code must
    only ever talk to this interface — never branch on which concrete broker is active."""

    @abstractmethod
    def place_order(self, order: OrderRequest) -> Fill:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> list[Position]:
        raise NotImplementedError

    @abstractmethod
    def get_position(self, symbol: str) -> Position:
        raise NotImplementedError

    @abstractmethod
    def get_funds(self) -> float:
        raise NotImplementedError
