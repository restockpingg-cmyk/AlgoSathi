"""Position-level exits: stop loss, target, trailing stop, and the intraday square-off.

These are the exits the *strategy* never asks for. A strategy only knows about its own
signals — it will happily sit in a position through a 5% drop because its exit condition has
not fired yet. Every serious intraday setup pairs the entry logic with a hard stop, a target,
and a time by which the position must be flat regardless. That is what this provides.

The guard is checked on every candle, ahead of the strategy, so a stop always wins over a
strategy signal on the same bar. It is stateful (it remembers the entry price and the
high-water mark) which is exactly why it does not live inside Strategy — strategies here are
pure functions of candle history and must stay that way.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from algosathi.config import ExitRulesConfig

# Every time rule here means a wall-clock time on the Indian exchanges. Candles arrive in
# different zones depending on the path — Supabase returns UTC, Upstox returns +05:30 — so
# "15:15" would silently mean two different market moments without normalising first.
EXCHANGE_TZ = ZoneInfo("Asia/Kolkata")


def _exchange_time(now: datetime) -> dtime:
    """The time of day at the exchange, whatever zone the caller's timestamp carries.
    A naive timestamp is assumed to already be exchange-local."""
    if now.tzinfo is None:
        return now.time()
    return now.astimezone(EXCHANGE_TZ).time()


@dataclass(frozen=True)
class GuardExit:
    reason: str
    kind: str  # "stop_loss" | "target" | "trailing_stop" | "square_off"


def _parse_time(value: str | None) -> dtime | None:
    """Accepts 'HH:MM' from YAML. None/empty means the rule is off."""
    if not value:
        return None
    hour, _, minute = value.partition(":")
    return dtime(int(hour), int(minute))


class PositionGuard:
    """Tracks one open long position and decides when it must be closed.

    All thresholds are percentages of the entry price, which keeps them meaningful across
    instruments priced anywhere from a ₹100 stock to a ₹24,000 index.
    """

    def __init__(self, config: ExitRulesConfig):
        self.stop_loss_pct = config.stop_loss_pct
        self.target_pct = config.target_pct
        self.trailing_stop_pct = config.trailing_stop_pct
        self.square_off_time = _parse_time(config.square_off_time)
        self.no_entry_before = _parse_time(config.no_entry_before)
        self.no_entry_after = _parse_time(config.no_entry_after)

        self.entry_price: float | None = None
        self.high_water: float | None = None

    # --- position lifecycle -------------------------------------------------

    def on_entry(self, price: float) -> None:
        self.entry_price = price
        self.high_water = price

    def on_exit(self) -> None:
        self.entry_price = None
        self.high_water = None

    @property
    def is_armed(self) -> bool:
        return self.entry_price is not None

    # --- checks -------------------------------------------------------------

    def entry_allowed(self, now: datetime) -> tuple[bool, str]:
        """Whether a new position may be opened at this time of day.

        Keeps the bot out of the opening auction's noise and stops it entering minutes
        before the square-off would close the trade at a loss anyway.
        """
        current = _exchange_time(now)
        if self.no_entry_before and current < self.no_entry_before:
            return False, f"before the {self.no_entry_before:%H:%M} entry window opens"
        if self.no_entry_after and current > self.no_entry_after:
            return False, f"after the {self.no_entry_after:%H:%M} entry cut-off"
        if self.square_off_time and current >= self.square_off_time:
            return False, f"past the {self.square_off_time:%H:%M} square-off"
        return True, ""

    def check(
        self,
        price: float,
        now: datetime,
        low: float | None = None,
        high: float | None = None,
    ) -> GuardExit | None:
        """Returns the exit that fired on this bar, if any.

        Pass the bar's low and high where you have them. A real stop-loss order rests at the
        exchange and triggers the moment price touches it, not at the candle's close — a
        5-minute bar can dip well through the stop and close back above it, and checking only
        the close would miss that entirely. Where low/high are omitted (a live tick, say) the
        single price stands in for all three.

        Ordering is worst-case on purpose: the stop is evaluated before the target, so a bar
        wide enough to touch both is scored as the loss. Assuming the win is how backtests
        flatter themselves.
        """
        # The square-off applies whether or not a position exists elsewhere, but only matters
        # when armed — callers check is_armed first for entries.
        if self.square_off_time and _exchange_time(now) >= self.square_off_time:
            return GuardExit(
                reason=f"intraday square-off at {self.square_off_time:%H:%M}", kind="square_off"
            )

        if self.entry_price is None:
            return None

        low = price if low is None else low
        high = price if high is None else high

        if self.stop_loss_pct:
            stop = self.entry_price * (1 - self.stop_loss_pct / 100)
            if low <= stop:
                return GuardExit(
                    reason=f"stop loss hit at {stop:.2f} ({self.stop_loss_pct}% below entry "
                    f"{self.entry_price:.2f})",
                    kind="stop_loss",
                )

        if self.trailing_stop_pct:
            # Give back at most trailing_stop_pct of the best price seen since entry. Before
            # price has moved up at all the high-water mark is still the entry, so this
            # coincides with a fixed stop of the same size — intended, not a case to code
            # around. The breach is checked against the *previous* high-water mark before
            # this bar's high raises it, otherwise a single wide bar could both set a new
            # high and be measured against it.
            trail = self.high_water * (1 - self.trailing_stop_pct / 100)
            if low <= trail:
                return GuardExit(
                    reason=f"trailing stop hit at {trail:.2f} ({self.trailing_stop_pct}% off "
                    f"the high of {self.high_water:.2f})",
                    kind="trailing_stop",
                )

        if self.high_water is None or high > self.high_water:
            self.high_water = high

        if self.target_pct:
            target = self.entry_price * (1 + self.target_pct / 100)
            if high >= target:
                return GuardExit(
                    reason=f"target hit at {target:.2f} ({self.target_pct}% above entry "
                    f"{self.entry_price:.2f})",
                    kind="target",
                )

        return None
