from __future__ import annotations

from abc import ABC, abstractmethod

from algosathi.core.models import Fill, OrderRequest, Position


class BrokerAdapter(ABC):
    """Common interface for paper and live brokers. Strategy, risk, and runner code must
    only ever talk to this interface — never branch on which concrete broker is active."""

    @abstractmethod
    def place_order(self, order: OrderRequest) -> Fill:
        raise NotImplementedError

    def place_resting_order(self, order: OrderRequest) -> str | None:
        """Submits an order that waits at the exchange rather than filling now, returning its
        broker order id.

        This is how a protective stop should work: it triggers on tick, not when the bot next
        polls. Brokers that cannot do this return None and the caller falls back to the
        polled PositionGuard.
        """
        return None

    def cancel_order(self, order_id: str) -> bool:
        """Cancels a resting order. Returns whether it was cancelled.

        Needed because a strategy exit and a resting stop are alternatives: whichever happens
        first, the other must be pulled or the account ends up short a position it never
        meant to open.
        """
        return False

    @abstractmethod
    def get_positions(self) -> list[Position]:
        raise NotImplementedError

    @abstractmethod
    def get_position(self, symbol: str) -> Position:
        raise NotImplementedError

    @abstractmethod
    def get_funds(self) -> float:
        raise NotImplementedError
