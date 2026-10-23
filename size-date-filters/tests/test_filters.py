"""The filter values as XeFM reads them: a label, and a match over an entry."""

import time
from types import SimpleNamespace

from size_date_filters import filters
from size_date_filters.logic import DAY, GB, MB


def entry(size=0, mtime=0.0):
    return SimpleNamespace(size=size, mtime=mtime, is_dir=False, name="f")


def test_every_filter_has_a_label_and_a_match():
    for value in (filters.OVER_100MB, filters.OVER_1GB,
                  filters.MODIFIED_TODAY, filters.MODIFIED_7_DAYS):
        assert set(value) == {"label", "match"}
        assert value["label"]


def test_size_filters():
    assert filters.OVER_100MB["match"](entry(size=200 * MB))
    assert not filters.OVER_100MB["match"](entry(size=50 * MB))
    assert filters.OVER_1GB["match"](entry(size=2 * GB))
    assert not filters.OVER_1GB["match"](entry(size=200 * MB))


def test_date_filters():
    now = time.time()
    assert filters.MODIFIED_TODAY["match"](entry(mtime=now))
    assert not filters.MODIFIED_TODAY["match"](entry(mtime=now - 2 * DAY))
    assert filters.MODIFIED_7_DAYS["match"](entry(mtime=now - 6 * DAY))
    assert not filters.MODIFIED_7_DAYS["match"](entry(mtime=now - 8 * DAY))
