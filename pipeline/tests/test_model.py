import numpy as np
import pandas as pd

from pipeline.features import FEATURES, corrected_electricity
from pipeline.model import training_rows


def test_weather_correction_removes_pure_temperature_effect():
    days = pd.date_range("2015-01-01", "2016-12-31", freq="D")
    temp = pd.Series(10 + 10 * np.sin(2 * np.pi * days.dayofyear / 365), index=days)
    daily = np.exp(11 + 0.02 * (15 - temp).clip(lower=0))  # consumption driven only by heating
    monthly = corrected_electricity(daily, temp, fit_until=days[-1])
    assert monthly.abs().max() < 1e-9


def test_training_uses_only_published_months_and_skips_covid():
    months = pd.period_range("2019-01", "2021-12", freq="M")
    f = pd.DataFrame(1.0, index=months, columns=["y", *FEATURES])
    train = training_rows(f, pd.Period("2021-06", "M"))
    assert train.index.max() == pd.Period("2021-04", "M")  # IPI known up to t-2
    assert pd.Period("2020-04", "M") not in train.index


def test_coverage_uses_only_errors_known_at_the_time():
    from pipeline.model import diagnostics

    months = pd.period_range("2021-01", "2024-12", freq="M")
    # Errors of 1 for three years, then a jump to 10: a range built from past errors must miss the jump.
    err = np.where(months < pd.Period("2024-01", "M"), 1.0, 10.0)
    bt = pd.DataFrame({"actual": 0.0, "ridge": err, "ar": 0.0, "gbm": 0.0}, index=months)
    for c in FEATURES:
        bt[f"w_{c}"] = 0.0
    cov = diagnostics(bt)["coverage"]
    assert cov["from"] == "2023-02"  # first month with 24 published errors (2021-01..2022-12)
    # Inside: 2023-02..2023-12 (11 months). 2024-01..11 miss: too few large errors known yet to widen
    # the range. 2024-12 is inside: by then 10 of the 46 known errors are large, so q80 reaches 10.
    assert cov["share"] == 12 / 23
