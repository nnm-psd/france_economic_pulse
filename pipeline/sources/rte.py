"""RTE éCO2mix national electricity consumption (MW), via ODRE.

History comes from the consolidated dataset (2012 to about 3 months ago); recent data
from the real-time one. Both are kept at 30-minute steps so a consolidated value
replaces the real-time one on the same key when RTE publishes it.
"""

from datetime import date, timedelta
from io import StringIO

import pandas as pd

from . import get

NAME = "rte"
KEY = ["date"]
PARTITION = "%Y-%m"
OVERLAP = timedelta(days=180)  # consolidated data lags ~3 months; re-read it as it lands
MAX_AGE = timedelta(days=2)

URL = "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/{}/exports/csv"
DATASETS = {"def": "eco2mix-national-cons-def", "tr": "eco2mix-national-tr"}


def parse(text: str, dataset: str) -> pd.DataFrame:
    df = pd.read_csv(StringIO(text), sep=";").dropna()
    t = pd.to_datetime(df["date_heure"], utc=True).dt.tz_localize(None)
    df = pd.DataFrame({"date": t, "consumption_mw": df["consommation"].astype("int64"), "dataset": dataset})
    return df[df["date"].dt.minute.isin([0, 30])]


def fetch(since: date | None) -> pd.DataFrame:
    frames = []
    for dataset, ident in DATASETS.items():
        where = "consommation is not null"
        if since:
            where += f' and date_heure >= "{since:%Y-%m-%d}"'
        frames.append(parse(get(URL.format(ident), select="date_heure,consommation", where=where), dataset))
    df = pd.concat(frames)
    # Where both datasets cover a time, the consolidated value wins.
    return df.sort_values("dataset").drop_duplicates("date", keep="first").sort_values("date")
