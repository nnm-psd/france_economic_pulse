"""Daily mean temperature for France, as a population-weighted mean of 8 large cities (Open-Meteo).

Used only to remove the heating/cooling effect from electricity consumption (D4).
Data: Open-Meteo historical weather API, CC BY 4.0.
"""

import json
from datetime import date, timedelta

import pandas as pd

from . import get

NAME = "weather"
KEY = ["date"]
PARTITION = "%Y"
OVERLAP = timedelta(days=10)  # recent days are preliminary and get replaced
MAX_AGE = timedelta(days=10)

URL = "https://archive-api.open-meteo.com/v1/archive"
START = date(2012, 1, 1)  # same start as the RTE history

# ponytail: approximate metro-area populations (millions) as weights, a proper
# degree-day weighting by region (e.g. RTE's reference temperature) if the correction underperforms.
CITIES = {
    "Paris": (48.86, 2.35, 13.1),
    "Lyon": (45.76, 4.84, 2.3),
    "Marseille": (43.30, 5.37, 1.9),
    "Toulouse": (43.60, 1.44, 1.5),
    "Lille": (50.63, 3.06, 1.5),
    "Bordeaux": (44.84, -0.58, 1.4),
    "Nantes": (47.22, -1.55, 1.0),
    "Strasbourg": (48.57, 7.75, 0.8),
}


def parse(text: str) -> pd.DataFrame:
    locations = json.loads(text)
    temps = pd.DataFrame({
        city: loc["daily"]["temperature_2m_mean"] for city, loc in zip(CITIES, locations)
    }, index=pd.to_datetime(locations[0]["daily"]["time"])).dropna()
    weights = pd.Series({city: w for city, (_, _, w) in CITIES.items()})
    mean = temps.mul(weights).sum(axis=1) / weights.sum()
    return pd.DataFrame({"date": mean.index, "temp_c": mean.round(2).to_numpy()})


def fetch(since: date | None) -> pd.DataFrame:
    lat, lon, _ = zip(*CITIES.values())
    return parse(get(
        URL,
        latitude=",".join(map(str, lat)),
        longitude=",".join(map(str, lon)),
        start_date=f"{since or START:%Y-%m-%d}",
        end_date=f"{date.today() - timedelta(days=1):%Y-%m-%d}",
        daily="temperature_2m_mean",
        timezone="Europe/Paris",
    ))
