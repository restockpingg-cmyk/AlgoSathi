"""When to poll.

Sleeping a fixed interval after each cycle sounds equivalent to polling every minute, but it
is not. It anchors the schedule to whatever second the process happened to start on, and
because the sleep begins *after* the work, every cycle is `interval + however long the API
calls took` — so the phase drifts all session. Start at 09:15:58 with 5-minute candles and
the 09:20:00 close is not noticed until 09:20:58.

Anchoring to the wall clock instead makes the delay a constant few seconds no matter when the
bot was started, and stops the drift accumulating.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# Upstox needs a moment to publish a candle after its period ends; polling exactly on the
# boundary tends to return the previous candle as the latest.
DEFAULT_SETTLE_SECONDS = 5.0


def next_candle_poll(
    now: datetime, interval_minutes: int, settle_seconds: float = DEFAULT_SETTLE_SECONDS
) -> datetime:
    """The next candle boundary after `now`, plus a settling buffer.

    Boundaries are measured from midnight, which puts a 5-minute grid on :00, :05, :10 … —
    the same grid the exchange uses, since NSE's 09:15 open is itself a whole number of
    minutes from midnight.
    """
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be > 0")

    period = timedelta(minutes=interval_minutes)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    periods_elapsed = int((now - midnight) // period)

    target = midnight + period * periods_elapsed + timedelta(seconds=settle_seconds)
    if target <= now:
        target = midnight + period * (periods_elapsed + 1) + timedelta(seconds=settle_seconds)
    return target


def seconds_until(target: datetime, now: datetime) -> float:
    """Never negative — a cycle that overran its slot should poll again immediately rather
    than sleep backwards."""
    return max(0.0, (target - now).total_seconds())
