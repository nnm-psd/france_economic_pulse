"""INSEE quarterly national accounts: real GDP (chained volumes, SA-WDA), the target of the GDP nowcast (D31).

Revised at every release, so the full history is re-fetched every run; each new release is archived (D8).
"""

from datetime import date, timedelta

import pandas as pd

from . import get
from .insee import URL, parse as parse_insee

NAME = "gdp"
KEY = ["date", "series"]
PARTITION = None
OVERLAP = None
MAX_AGE = timedelta(days=220)  # dated at quarter start; the next quarter comes ~4 months after that, plus slack

SERIES = {"011794860": "gdp"}  # Total GDP, volumes chained at previous year prices, SA-WDA, base 2020


def parse(xml: str) -> pd.DataFrame:
    return parse_insee(xml, SERIES)


def fetch(since: date | None) -> pd.DataFrame:
    return parse(get(URL.format("+".join(SERIES))))
