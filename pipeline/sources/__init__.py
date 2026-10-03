"""One module per source. Each exposes NAME, KEY, PARTITION, OVERLAP, MAX_AGE, parse(text) and fetch(since).

OVERLAP: how far back to re-fetch before the last stored date, to pick up revisions.
None means re-fetch the full history every run (small series that get revised).
PARTITION: strftime pattern for storage files, or None for one file (see store.save).
MAX_AGE: how old the newest stored point may be before the freshness check fails.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HEADERS = {"User-Agent": "france-economic-pulse (+https://github.com/nnm-psd/france_economic_pulse)"}

# Providers occasionally time out or return a temporary error: retry 3 times (waits 2, 4, 8 s) before failing.
session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])))


def get(url: str, **params) -> str:
    r = session.get(url, params=params, headers=HEADERS, timeout=120)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text.lstrip("﻿")
