from datetime import datetime, timedelta

import pytest

from algosathi.config import ExitRulesConfig
from algosathi.risk.position_guard import PositionGuard

AT_1000 = datetime(2026, 1, 1, 10, 0)


def guard(**kwargs) -> PositionGuard:
    return PositionGuard(ExitRulesConfig(**kwargs))


def test_nothing_fires_when_no_rules_are_set():
    g = guard()
    g.on_entry(100.0)
    assert g.check(50.0, AT_1000) is None
    assert g.check(500.0, AT_1000) is None


def test_nothing_fires_before_entry():
    g = guard(stop_loss_pct=1.0)
    assert g.check(1.0, AT_1000) is None


def test_stop_loss_fires_at_the_threshold_not_before():
    g = guard(stop_loss_pct=2.0)
    g.on_entry(100.0)
    assert g.check(98.5, AT_1000) is None
    hit = g.check(98.0, AT_1000)
    assert hit is not None and hit.kind == "stop_loss"


def test_target_fires_at_the_threshold():
    g = guard(target_pct=3.0)
    g.on_entry(100.0)
    assert g.check(102.9, AT_1000) is None
    hit = g.check(103.0, AT_1000)
    assert hit is not None and hit.kind == "target"


def test_stop_wins_over_target_on_a_bar_that_touches_both():
    """A bar wide enough to hit both must be scored as the loss — assuming the win is how
    backtests flatter themselves."""
    g = guard(stop_loss_pct=2.0, target_pct=2.0)
    g.on_entry(100.0)
    hit = g.check(100.0, AT_1000, low=97.0, high=103.0)
    assert hit is not None and hit.kind == "stop_loss"


def test_stop_fires_intrabar_even_when_the_close_recovers():
    """A real stop rests at the exchange; a dip through it counts even if the candle closes
    back above."""
    g = guard(stop_loss_pct=2.0)
    g.on_entry(100.0)
    hit = g.check(99.5, AT_1000, low=97.5, high=100.5)
    assert hit is not None and hit.kind == "stop_loss"


def test_target_fires_intrabar_on_the_high():
    g = guard(target_pct=3.0)
    g.on_entry(100.0)
    hit = g.check(101.0, AT_1000, low=100.0, high=103.5)
    assert hit is not None and hit.kind == "target"


def test_trailing_stop_follows_the_high_water_mark():
    g = guard(trailing_stop_pct=2.0)
    g.on_entry(100.0)

    assert g.check(110.0, AT_1000) is None  # new high, nothing given back yet
    assert g.check(108.5, AT_1000) is None  # 1.4% off the high, still inside
    hit = g.check(107.8, AT_1000)  # 2% off 110
    assert hit is not None and hit.kind == "trailing_stop"


def test_trailing_stop_never_moves_down():
    g = guard(trailing_stop_pct=5.0)
    g.on_entry(100.0)
    g.check(120.0, AT_1000)
    g.check(115.0, AT_1000)  # pulls back but does not breach
    assert g.high_water == 120.0
    hit = g.check(114.0, AT_1000)  # 5% off 120
    assert hit is not None and hit.kind == "trailing_stop"


def test_square_off_fires_on_time_regardless_of_price():
    g = guard(square_off_time="15:15")
    g.on_entry(100.0)
    assert g.check(100.0, datetime(2026, 1, 1, 15, 14)) is None
    hit = g.check(100.0, datetime(2026, 1, 1, 15, 15))
    assert hit is not None and hit.kind == "square_off"


def test_entry_window_blocks_outside_the_configured_hours():
    g = guard(no_entry_before="09:20", no_entry_after="15:00", square_off_time="15:15")
    assert g.entry_allowed(datetime(2026, 1, 1, 9, 16))[0] is False
    assert g.entry_allowed(datetime(2026, 1, 1, 9, 20))[0] is True
    assert g.entry_allowed(datetime(2026, 1, 1, 14, 59))[0] is True
    assert g.entry_allowed(datetime(2026, 1, 1, 15, 1))[0] is False


def test_exit_disarms_the_guard():
    g = guard(stop_loss_pct=1.0)
    g.on_entry(100.0)
    assert g.is_armed
    g.on_exit()
    assert not g.is_armed
    assert g.check(1.0, AT_1000) is None


@pytest.mark.parametrize("value,expected", [("09:20", True), (None, False)])
def test_unset_time_rules_are_off(value, expected):
    g = guard(no_entry_before=value)
    assert (g.no_entry_before is not None) is expected


def test_time_rules_use_exchange_time_not_the_timestamp_zone():
    """Supabase hands back UTC and Upstox hands back +05:30. 09:15 IST is 03:45 UTC — the
    same market moment — and a time rule must treat them identically or a backtest and the
    live bot silently disagree about when the day starts."""
    from datetime import timezone

    g = guard(no_entry_before="09:20", square_off_time="15:15")

    utc_0915_ist = datetime(2026, 6, 8, 3, 45, tzinfo=timezone.utc)
    ist_0915 = datetime(2026, 6, 8, 9, 15, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert g.entry_allowed(utc_0915_ist)[0] is False
    assert g.entry_allowed(ist_0915)[0] is False

    utc_0930_ist = datetime(2026, 6, 8, 4, 0, tzinfo=timezone.utc)
    ist_0930 = datetime(2026, 6, 8, 9, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert g.entry_allowed(utc_0930_ist)[0] is True
    assert g.entry_allowed(ist_0930)[0] is True

    # Square-off likewise: 15:15 IST is 09:45 UTC.
    g.on_entry(100.0)
    assert g.check(100.0, datetime(2026, 6, 8, 9, 45, tzinfo=timezone.utc)).kind == "square_off"
