"""INSEE BDM monthly series: industrial production (the nowcast target) and business climate.

INSEE revises past months, so the full history is re-fetched every run.
"""

from datetime import date, timedelta
from xml.etree import ElementTree

import pandas as pd

from . import get

NAME = "insee"
KEY = ["date", "series"]
PARTITION = None
OVERLAP = None
MAX_AGE = timedelta(days=110)  # dated at month start, published ~40 days after month end

URL = "https://bdm.insee.fr/series/sdmx/data/SERIES_BDM/{}"
SERIES = {
    "010768261": "ipi_industry",  # SA-WDA IPI, base 2021, NAF A10 BE (target)
    "010768307": "ipi_manufacturing",  # SA-WDA IPI, base 2021, NAF A10 CZ
    "001565530": "business_climate",  # Business climate, all sectors, metropolitan France
}
TARGET = ["ipi_industry", "ipi_manufacturing"]


def parse(xml: str) -> pd.DataFrame:
    rows = [
        (obs.get("TIME_PERIOD"), SERIES[series.get("IDBANK")], float(obs.get("OBS_VALUE")))
        for series in ElementTree.fromstring(xml).iter()
        if series.tag.endswith("Series")
        for obs in series
        if obs.get("OBS_VALUE") not in (None, "NaN")
    ]
    df = pd.DataFrame(rows, columns=["date", "series", "value"])
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m")
    return df.sort_values(KEY).reset_index(drop=True)


def fetch(since: date | None) -> pd.DataFrame:
    return parse(get(URL.format("+".join(SERIES))))
