"""The filters, in the shape config.py's FILTERS takes: a row label and a
function from an entry to "show it". The clock is read when the filter runs,
so "today" moves on at midnight without reloading anything."""

import time

from size_date_filters.logic import (
    DAY, GB, MB, larger_than, modified_since, start_of_day)

OVER_100MB = {"label": "Over 100 MB",
              "match": lambda e: larger_than(e.size, 100 * MB)}

OVER_1GB = {"label": "Over 1 GB",
            "match": lambda e: larger_than(e.size, GB)}

MODIFIED_TODAY = {"label": "Modified today",
                  "match": lambda e: modified_since(e.mtime,
                                                    start_of_day(time.time()))}

MODIFIED_7_DAYS = {"label": "Modified in the last 7 days",
                   "match": lambda e: modified_since(e.mtime,
                                                     time.time() - 7 * DAY)}
