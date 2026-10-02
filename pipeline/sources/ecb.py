"""ECB long-term interest rates (10-year government bonds), France and Germany, monthly.

Small and occasionally revised, so the full history is re-fetched every run.
"""

from datetime import date, timedelta
from io import StringIO

import pandas as pd

from . import get

NAME = "ecb"
KEY = ["date", "series"]
PARTITION = None
OVERLAP = None
MAX_AGE = timedelta(days=100)  # dated at month start, published ~1 month after month end

URL = "https://data-api.ecb.europa.eu/service/data/IRS/M.FR+DE.L.L40.CI.0000.EUR.N.Z"


def parse(text: str) -> pd.DataFrame:
    df = pd.read_csv(StringIO(text), usecols=["REF_AREA", "TIME_PERIOD", "OBS_VALUE"]).dropna()
    return pd.DataFrame({
        "date": pd.to_datetime(df["TIME_PERIOD"], format="%Y-%m"),
        "series": "yield_10y_" + df["REF_AREA"].str.lower(),
        "value": df["OBS_VALUE"].astype(float),
    }).sort_values(KEY).reset_index(drop=True)


def fetch(since: date | None) -> pd.DataFrame:
    return parse(get(URL, format="csvdata"))
