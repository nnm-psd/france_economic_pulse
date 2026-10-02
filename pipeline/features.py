"""Monthly feature table for the nowcast (D4, D12).

Timing: the nowcast for month t is made at the start of month t+1. At that point
INSEE has published industrial production only up to t-2, ECB yields up to t-1,
and electricity, temperature, business climate and insolvencies are complete for t.
Every feature below is lagged to match.
"""

import numpy as np
import pandas as pd

from . import store

SOURCES = ["rte", "weather", "insee", "ecb", "bodacc"]
HDD_BASE, CDD_BASE = 15.0, 20.0  # °C: heating below, cooling above
MIN_DAYS = 25  # a month needs this many complete days of electricity data

FEATURES = [
    "y_lag2",  # latest published IPI growth
    "elec", "elec_lag1",  # weather-corrected electricity growth
    "climate", "climate_chg",  # INSEE business climate, level vs 100 and change
    "insolv_yoy",  # insolvency openings, year-on-year
    "spread_lag1", "spread_chg_lag1",  # FR-DE 10-year spread, bp
]


def load_raw() -> dict[str, pd.DataFrame]:
    return {name: store.load(name) for name in SOURCES}


def daily_electricity(rte: pd.DataFrame) -> pd.Series:
    """Daily mean consumption (MW) by French calendar day, complete days only."""
    day = rte["date"].dt.tz_localize("UTC").dt.tz_convert("Europe/Paris").dt.tz_localize(None).dt.normalize()
    g = rte.groupby(day)["consumption_mw"]
    return g.mean()[g.count() >= 40]  # 48 half-hours a day (46/50 on DST change days)


def corrected_electricity(daily: pd.Series, temp: pd.Series, fit_until: pd.Timestamp) -> pd.Series:
    """Monthly mean of log consumption after removing temperature, weekday and calendar-month effects (D4).

    The coefficients are fitted only on days before `fit_until`, so a backtest never sees the future.
    """
    df = pd.DataFrame({"y": np.log(daily)}).join(temp.rename("t"), how="inner")
    idx = df.index
    X = pd.concat([
        pd.DataFrame({
            "const": 1.0,
            "hdd": (HDD_BASE - df["t"]).clip(lower=0),
            "cdd": (df["t"] - CDD_BASE).clip(lower=0),
        }, index=idx),
        pd.get_dummies(idx.dayofweek, prefix="dow", drop_first=True, dtype=float).set_index(idx),
        pd.get_dummies(idx.month, prefix="m", drop_first=True, dtype=float).set_index(idx),
    ], axis=1)
    # ponytail: no public-holiday dummies, add them if monthly residuals show holiday noise.
    fit = idx < fit_until
    beta, *_ = np.linalg.lstsq(X[fit].to_numpy(), df["y"][fit].to_numpy(), rcond=None)
    resid = df["y"] - X.to_numpy() @ beta
    month = resid.groupby(idx.to_period("M"))
    return month.mean()[month.count() >= MIN_DAYS]


def monthly_features(raw: dict[str, pd.DataFrame], fit_until: pd.Timestamp) -> pd.DataFrame:
    """One row per month: target `y` (IPI growth, %) and FEATURES, aligned to the nowcast timing."""
    def wide(df):
        w = df.pivot(index="date", columns="series", values="value")
        w.index = w.index.to_period("M")
        return w

    insee, ecb = wide(raw["insee"]), wide(raw["ecb"])
    temp = raw["weather"].set_index("date")["temp_c"]
    elec = corrected_electricity(daily_electricity(raw["rte"]), temp, fit_until)
    openings = raw["bodacc"].set_index("date")["openings"]
    openings = openings.groupby(openings.index.to_period("M")).sum()

    months = pd.period_range(insee.index.min(), max(elec.index.max(), insee.index.max()), freq="M")
    on = lambda s: s.reindex(months)
    spread = on(ecb["yield_10y_fr"] - ecb["yield_10y_de"]) * 100
    climate = on(insee["business_climate"])

    f = pd.DataFrame(index=months)
    f["y"] = 100 * np.log(on(insee["ipi_industry"])).diff()
    f["y_lag2"] = f["y"].shift(2)
    f["elec"] = 100 * on(elec).diff()
    f["elec_lag1"] = f["elec"].shift(1)
    f["climate"] = climate - 100
    f["climate_chg"] = climate.diff()
    f["insolv_yoy"] = 100 * np.log(on(openings)).diff(12)
    f["spread_lag1"] = spread.shift(1)
    f["spread_chg_lag1"] = spread.diff().shift(1)
    return f
