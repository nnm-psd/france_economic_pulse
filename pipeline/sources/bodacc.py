"""BODACC: daily count of insolvency proceedings opened in France (since 2008).

Counts initial "Procédures collectives" notices whose judgment mentions "ouverture"
(safeguard, receivership, liquidation openings). Days without a publication have no row.
"""

from datetime import date, timedelta
from io import StringIO

import pandas as pd

from . import get

NAME = "bodacc"
KEY = ["date"]
PARTITION = "%Y"
OVERLAP = timedelta(days=14)  # late corrections and cancellations
MAX_AGE = timedelta(days=5)  # no publication on some weekends and holidays

URL = "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/annonces-commerciales/exports/csv"
WHERE = 'familleavis="collective" and typeavis="annonce" and search(jugement, "ouverture")'


def parse(text: str) -> pd.DataFrame:
    df = pd.read_csv(StringIO(text), sep=";")
    return pd.DataFrame({
        "date": pd.to_datetime(df["dateparution"], utc=True).dt.tz_localize(None),
        "openings": df["n"].astype("int64"),
    }).sort_values("date").reset_index(drop=True)


def fetch(since: date | None) -> pd.DataFrame:
    where = WHERE + (f' and dateparution >= "{since:%Y-%m-%d}"' if since else "")
    return parse(get(URL, select="dateparution,count(*) as n", group_by="dateparution", where=where))
