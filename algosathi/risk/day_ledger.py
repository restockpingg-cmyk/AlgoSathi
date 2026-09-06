"""Today's realized P&L, derived from the trade log rather than the broker.

The daily-loss circuit breaker is the last thing standing between a bad strategy and a bad
day. It was reading `broker.realized_pnl`, which only PaperBroker has — so in live mode it
silently read 0.0 and the limit could never trip. A safety limit that is inert precisely in
the mode where real money is at stake is worse than no limit, because it reads as protection.

Deriving it from the persisted trades instead means it is correct for any broker, and it
survives a mid-day restart: a bot that crashes after losing its limit and comes back thinking
the day started fresh would carry straight on losing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


from sqlalchemy.orm import Session, sessionmaker

from algosathi.core.enums import Mode
from algosathi.persistence.models import Trade


@dataclass(frozen=True)
class DayPnl:
    """Today's result, before and after what it cost to trade.

    Both are reported because on a small edge they disagree by more than the edge: showing
    only the gross number makes a losing system look profitable, and showing only the net one
    hides whether the strategy or the costs are the problem.
    """

    gross: float
    charges: float

    @property
    def net(self) -> float:
        return self.gross - self.charges


def day_pnl(
    session_factory: sessionmaker[Session], mode: Mode, today: date | None = None
) -> DayPnl:
    """Weighted-average-cost realized P&L across every symbol traded today.

    Matches analytics.summarize_by_symbol's accounting so the circuit breaker and the reports
    can never disagree about what the day cost.
    """
    today = today or date.today()
    start = datetime.combine(today, datetime.min.time())

    with session_factory() as session:
        trades = (
            session.query(Trade)
            .filter(Trade.mode == mode.value, Trade.timestamp >= start)
            .order_by(Trade.timestamp)
            .all()
        )

    realized = 0.0
    charges = 0.0
    quantities: dict[str, int] = {}
    avg_costs: dict[str, float] = {}

    for trade in trades:
        symbol = trade.symbol
        held = quantities.get(symbol, 0)
        avg = avg_costs.get(symbol, 0.0)
        # Charges are paid on every leg, including the ones still holding an open position.
        charges += trade.charges or 0.0

        if trade.side == "buy":
            new_held = held + trade.quantity
            avg_costs[symbol] = (avg * held + trade.price * trade.quantity) / new_held
            quantities[symbol] = new_held
        else:
            realized += (trade.price - avg) * trade.quantity
            remaining = held - trade.quantity
            quantities[symbol] = remaining
            if remaining <= 0:
                avg_costs[symbol] = 0.0

    return DayPnl(gross=realized, charges=charges)


def realized_pnl_today(
    session_factory: sessionmaker[Session], mode: Mode, today: date | None = None
) -> float:
    """Net of charges — this is what the daily-loss circuit breaker must measure, because
    charges come out of the same account the losses do."""
    return day_pnl(session_factory, mode, today).net


def open_positions(session_factory: sessionmaker[Session], mode: Mode) -> dict[str, int]:
    """Net quantity held per symbol according to the trade log, for symbols still open.

    Used to restore state after a restart: without it a bot that comes back mid-session
    believes it is flat, re-enters symbols it already holds, and leaves the positions it does
    hold without a stop.
    """
    with session_factory() as session:
        trades = (
            session.query(Trade).filter(Trade.mode == mode.value).order_by(Trade.timestamp).all()
        )

    quantities: dict[str, int] = {}
    for trade in trades:
        delta = trade.quantity if trade.side == "buy" else -trade.quantity
        quantities[trade.symbol] = quantities.get(trade.symbol, 0) + delta

    return {symbol: qty for symbol, qty in quantities.items() if qty > 0}
