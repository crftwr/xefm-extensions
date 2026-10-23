"""Plain functions with no XeFM in them — what the tests exercise.

A filter is handed one entry at a time, on a background thread, and only for
files: XeFM always shows directories. ``size`` and ``mtime`` were collected
for the listing already, so reading them costs nothing.
"""

import time

MB = 1 << 20
GB = 1 << 30
DAY = 24 * 3600


def larger_than(size, limit):
    """True when ``size`` (bytes) is over ``limit``. An unknown size is not."""
    return size is not None and size > limit


def start_of_day(now):
    """Local midnight of the day ``now`` (a Unix time) falls on.

    Built from the local calendar date rather than ``now - now % DAY``, which
    would be midnight UTC, and through ``mktime``, so a day that is 23 or 25
    hours long (a daylight-saving change) still starts at its own midnight."""
    t = time.localtime(now)
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))


def modified_since(mtime, since):
    """True when ``mtime`` is at or after ``since``. An unknown time is not."""
    return mtime is not None and mtime >= since
