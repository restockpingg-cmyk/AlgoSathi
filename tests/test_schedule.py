from datetime import datetime

import pytest

from algosathi.schedule import next_candle_poll, seconds_until


def at(hour, minute, second=0):
    return datetime(2026, 3, 10, hour, minute, second)


def test_snaps_to_the_candle_grid_whatever_second_you_start_on():
    """The whole point: the start time must not set the schedule's phase for the rest of the
    session, which is what a plain sleep(60) does."""
    for start in (at(9, 17, 23), at(9, 15, 58), at(9, 19, 59), at(9, 16, 0)):
        assert next_candle_poll(start, interval_minutes=5) == at(9, 20, 5)


def test_polls_just_after_the_close_not_exactly_on_it():
    """Upstox needs a moment to publish the completed candle; asking on the boundary tends to
    return the previous one."""
    assert next_candle_poll(at(9, 20, 0), interval_minutes=5) == at(9, 20, 5)


def test_a_boundary_already_passed_moves_to_the_next_one():
    assert next_candle_poll(at(9, 20, 6), interval_minutes=5) == at(9, 25, 5)
    assert next_candle_poll(at(9, 20, 5), interval_minutes=5) == at(9, 25, 5)


def test_one_minute_candles_land_on_every_minute():
    assert next_candle_poll(at(9, 17, 23), interval_minutes=1) == at(9, 18, 5)


def test_fifteen_minute_candles_land_on_the_quarter_hour():
    assert next_candle_poll(at(9, 17, 23), interval_minutes=15) == at(9, 30, 5)


def test_the_grid_matches_the_exchange_open():
    """NSE opens at 09:15, which is a whole number of 5-minute periods from midnight — so a
    midnight-anchored grid lines up with the exchange's own candles."""
    assert next_candle_poll(at(9, 14, 59), interval_minutes=5) == at(9, 15, 5)


def test_a_cycle_that_overran_its_slot_polls_immediately():
    """Sleeping a negative duration would throw; falling behind should just mean going again
    now, not skipping a candle."""
    assert seconds_until(at(9, 20, 5), now=at(9, 21, 0)) == 0.0


def test_normal_wait_is_the_real_gap():
    assert seconds_until(at(9, 20, 5), now=at(9, 19, 5)) == 60.0


def test_rejects_a_nonsense_interval():
    with pytest.raises(ValueError):
        next_candle_poll(at(9, 17), interval_minutes=0)
