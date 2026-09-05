"""A mechanical approximation of Elliott Wave theory.

Real Elliott Wave analysis is a fractal, discretionary craft: two analysts looking at the
same chart routinely disagree on the count, and counts get relabelled after the fact. None
of that can be automated honestly. What *can* be automated is the small subset of Elliott's
rules that are objective and checkable bar-by-bar:

  * Waves alternate between impulse and correction, so the price structure is a sequence of
    swing highs and lows (found here with a causal zig-zag, see `find_pivots`).
  * Wave 2 never retraces more than 100% of wave 1 -- it must bottom above wave 1's origin.
    In practice it usually retraces a Fibonacci 38.2%-78.6% of it.
  * Wave 3 is the strongest leg, is never the shortest, and commonly extends to about
    1.618x wave 1 measured from the wave 2 low.

So this strategy waits for a completed 1-2 (low -> high -> higher low), checks those rules,
and buys the break above the wave 1 top -- i.e. it tries to ride wave 3 and nothing else.
It does NOT attempt to count waves 4 and 5, label corrective A-B-C patterns, or reason
about degree/nesting. Treat it as "trade the third wave", not as an Elliott Wave analyst.

Because the zig-zag only confirms a pivot once price has reversed by the threshold, every
pivot used here was already knowable at the bar it is used on -- there is no repainting and
no look-ahead. The cost is lag: the wave 2 low is confirmed some bars after it prints.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from algosathi.core.enums import SignalType
from algosathi.core.models import Signal
from algosathi.strategy.base import Strategy


@dataclass(frozen=True)
class Pivot:
    """A confirmed swing point.

    `index` is the bar the extreme actually printed on; `confirmed_at` is the later bar on
    which price had reversed far enough for us to call it a pivot. Only `confirmed_at` is
    "now" — anything keyed off `index` alone would be look-ahead.
    """

    index: int
    price: float
    kind: str  # "high" | "low"
    confirmed_at: int


def find_pivots(candles: pd.DataFrame, threshold_pct: float) -> list[Pivot]:
    """Causal zig-zag: alternating swing highs and lows, where a swing is only recognised
    once price has retraced `threshold_pct` percent away from the extreme.

    Unlike the usual charting zig-zag this never revises a pivot once emitted, which is what
    makes it safe to use inside a bar-by-bar simulation.
    """
    highs = candles["high"].to_numpy(dtype=float)
    lows = candles["low"].to_numpy(dtype=float)
    if len(highs) == 0:
        return []

    threshold = threshold_pct / 100.0
    pivots: list[Pivot] = []
    direction = 0  # 0 = undecided, 1 = tracking a swing high, -1 = tracking a swing low
    high_idx, high_price = 0, highs[0]
    low_idx, low_price = 0, lows[0]

    for i in range(1, len(highs)):
        high, low = highs[i], lows[i]

        if direction >= 0 and high > high_price:
            high_idx, high_price = i, high
        if direction <= 0 and low < low_price:
            low_idx, low_price = i, low

        if direction >= 0 and low <= high_price * (1 - threshold):
            pivots.append(Pivot(high_idx, high_price, "high", i))
            direction = -1
            # This bar broke the threshold, so its low is the lowest since that pivot.
            low_idx, low_price = i, low
        elif direction <= 0 and high >= low_price * (1 + threshold):
            pivots.append(Pivot(low_idx, low_price, "low", i))
            direction = 1
            high_idx, high_price = i, high

    return pivots


class ElliottWaveStrategy(Strategy):
    """Long-only wave-3 rider.

    BUY  — the last three pivots form a valid wave 1-2 (low, high, higher low), wave 2's
           retracement of wave 1 sits in the Fibonacci band, and close breaks above the
           wave 1 top.
    EXIT — whichever comes first of: a new swing high confirming (wave 3 has topped),
           close reaching the 1.618 wave-3 projection, or close breaking back below the
           wave 2 low (the count was wrong).

    Like every other strategy here this stays a pure function of candle history — the wave
    context is re-derived from the pivots on each bar rather than remembered between calls.
    """

    def __init__(
        self,
        symbol: str,
        zigzag_pct: float = 0.5,
        min_retracement: float = 0.382,
        max_retracement: float = 0.786,
        target_extension: float = 1.618,
    ):
        if zigzag_pct <= 0:
            raise ValueError("zigzag_pct must be > 0")
        if not 0 < min_retracement < max_retracement < 1:
            raise ValueError("need 0 < min_retracement < max_retracement < 1")
        self.symbol = symbol
        self.zigzag_pct = zigzag_pct
        self.min_retracement = min_retracement
        self.max_retracement = max_retracement
        self.target_extension = target_extension

    def _signal(self, signal_type: SignalType, reason: str, timestamp) -> Signal:
        return Signal(
            symbol=self.symbol,
            signal_type=signal_type,
            reason=reason,
            timestamp=timestamp,
        )

    def on_candles(self, candles: pd.DataFrame) -> Signal | None:
        if len(candles) < 2:
            return None

        pivots = find_pivots(candles, self.zigzag_pct)
        if len(pivots) < 3:
            return None

        last_bar = len(candles) - 1
        prev_close = float(candles["close"].iloc[-2])
        curr_close = float(candles["close"].iloc[-1])
        timestamp = candles["timestamp"].iloc[-1]

        # A swing high confirming means price has already reversed by the zig-zag threshold
        # off its peak — as far as this strategy is concerned, wave 3 is over.
        latest = pivots[-1]
        if latest.kind == "high" and latest.confirmed_at == last_bar:
            return self._signal(
                SignalType.EXIT,
                f"swing high confirmed at {latest.price:.2f} — wave 3 assumed complete",
                timestamp,
            )

        wave0, wave1_top, wave2_low = pivots[-3], pivots[-2], pivots[-1]
        if not (wave0.kind == "low" and wave1_top.kind == "high" and wave2_low.kind == "low"):
            return None

        wave1_size = wave1_top.price - wave0.price
        if wave1_size <= 0:
            return None

        target = wave2_low.price + self.target_extension * wave1_size
        if prev_close < target <= curr_close:
            return self._signal(
                SignalType.EXIT,
                f"wave-3 target {target:.2f} ({self.target_extension}x wave 1) reached",
                timestamp,
            )

        if prev_close >= wave2_low.price > curr_close:
            return self._signal(
                SignalType.EXIT,
                f"close broke below the wave-2 low {wave2_low.price:.2f} — count invalidated",
                timestamp,
            )

        # Elliott's hard rule: wave 2 may not retrace all of wave 1.
        if not wave0.price < wave2_low.price < wave1_top.price:
            return None

        retracement = (wave1_top.price - wave2_low.price) / wave1_size
        if not self.min_retracement <= retracement <= self.max_retracement:
            return None

        if prev_close <= wave1_top.price < curr_close:
            return self._signal(
                SignalType.BUY,
                f"broke above wave-1 top {wave1_top.price:.2f} after a "
                f"{retracement:.1%} wave-2 retracement — wave 3 entry",
                timestamp,
            )

        return None
