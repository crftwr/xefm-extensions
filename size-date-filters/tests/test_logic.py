import time

from size_date_filters.logic import (
    DAY, GB, MB, larger_than, modified_since, start_of_day)


def test_larger_than_is_strict():
    assert larger_than(100 * MB + 1, 100 * MB)
    assert not larger_than(100 * MB, 100 * MB)
    assert not larger_than(0, MB)


def test_unknown_size_never_matches():
    assert not larger_than(None, 0)


def test_start_of_day_is_local_midnight():
    now = time.mktime((2026, 10, 23, 15, 30, 0, 0, 0, -1))
    midnight = start_of_day(now)
    t = time.localtime(midnight)
    assert (t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec) == \
        (2026, 10, 23, 0, 0, 0)
    assert 0 <= now - midnight < 25 * 3600


def test_start_of_day_at_midnight_is_itself():
    midnight = time.mktime((2026, 10, 23, 0, 0, 0, 0, 0, -1))
    assert start_of_day(midnight) == midnight


def test_modified_since():
    assert modified_since(100.0, 100.0)
    assert not modified_since(99.9, 100.0)
    assert not modified_since(None, 0)
