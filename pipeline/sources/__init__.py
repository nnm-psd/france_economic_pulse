"""One module per source. Each exposes NAME, KEY, PARTITION, OVERLAP, MAX_AGE, parse(text) and fetch(since).

OVERLAP: how far back to re-fetch before the last stored date, to pick up revisions.
None means re-fetch the full history every run (small series that get revised).
PARTITION: strftime pattern for storage files, or None for one file (see store.save).
MAX_AGE: how old the newest stored point may be before the freshness check fails.
"""

import requests

HEADERS = {"User-Agent": "france-economic-pulse (+https://github.com/nnm-psd/france_economic_pulse)"}


def get(url: str, **params) -> str:
    r = requests.get(url, params=params, headers=HEADERS, timeout=120)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text.lstrip("﻿")
