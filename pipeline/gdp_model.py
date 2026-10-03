"""Quarterly GDP nowcast: a bridge equation from monthly data to quarterly GDP growth (D31).

y_q = 100 * ln(GDP_q / GDP_{q-1}), explained by quarterly industrial production growth (months INSEE hasn't
published are filled by the monthly nowcast), INSEE's all-sector business climate and last quarter's growth.

Run with `uv run gdp-backtest` after `uv run backtest`: walk-forward from 2016Q1, as known at INSEE's first
GDP estimate (~30 days after the quarter): months 1-2 of industrial production published, month 3 replaced by
the monthly model's own walk-forward estimate. Writes data/model/gdp_backtest.parquet.
"""

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import load_raw
from .model import RIDGE_ALPHAS
from .store import DATA

START = pd.Period("2016Q1", "Q")  # the monthly backtest starts in 2016-01
# Out of training and of the "normal quarters" score: lockdowns ran until May 2021, and the reopening rebound
# (2021Q2-Q3) is pandemic-driven. Extended from 2021Q1 after seeing the 2021Q3 miss: both scores are published (D31).
COVID = pd.period_range("2020Q1", "2021Q4", freq="Q")
FEATURES = ["ipi_q", "climate_q", "climate_chg_q", "y_lag1"]
MODELS = {
    "mean": (["y_lag1"], lambda: DummyRegressor(strategy="mean")),  # historical average growth
    "ar": (["y_lag1"], LinearRegression),
    "bridge": (["ipi_q"], LinearRegression),  # the classic bridge: GDP growth on industrial production growth
    "ridge": (FEATURES, lambda: make_pipeline(StandardScaler(), RidgeCV(alphas=RIDGE_ALPHAS))),  # first spec (D31)
}


def monthly(raw, series: str) -> pd.Series:
    s = raw["insee"].query("series == @series").set_index("date")["value"]
    s.index = s.index.to_period("M")
    return s


def quarterly(raw, ipi: pd.Series) -> pd.DataFrame:
    """One row per quarter. `ipi` is monthly industrial production (PeriodIndex), possibly with estimated months."""
    gdp = raw["gdp"].set_index("date")["value"]
    gdp.index = gdp.index.to_period("Q")
    by_q = lambda s: s.groupby(s.index.asfreq("Q")).agg(["mean", "count"])
    ipi_q, climate = by_q(ipi), by_q(monthly(raw, "business_climate"))
    ipi_level = ipi_q["mean"][ipi_q["count"] == 3]  # complete quarters only
    climate_q = climate["mean"][climate["count"] == 3]
    quarters = pd.period_range(gdp.index.min(), max(gdp.index.max(), ipi_level.index.max()), freq="Q")
    on = lambda s: s.reindex(quarters)
    q = pd.DataFrame(index=quarters)
    q["y"] = 100 * np.log(on(gdp)).diff()
    q["y_lag1"] = q["y"].shift(1)
    q["ipi_q"] = 100 * np.log(on(ipi_level)).diff()
    q["climate_q"] = on(climate_q) - 100
    q["climate_chg_q"] = on(climate_q).diff()
    return q


def training(q: pd.DataFrame, before: pd.Period) -> pd.DataFrame:
    return q.loc[: before - 1].drop(COVID, errors="ignore").dropna(subset=["y", *FEATURES])


def fit_predict(train: pd.DataFrame, target: pd.DataFrame) -> dict[str, np.ndarray]:
    return {name: make().fit(train[cols], train["y"]).predict(target[cols]) for name, (cols, make) in MODELS.items()}


def backtest(raw, monthly_bt: pd.DataFrame) -> pd.DataFrame:
    ipi = monthly(raw, "ipi_industry")
    last = raw["gdp"]["date"].max().to_period("Q")
    rows = []
    for t in pd.period_range(START, last, freq="Q"):
        m1, m2, m3 = pd.period_range(t.asfreq("M", "start"), periods=3, freq="M")
        if m3 not in monthly_bt.index or m2 not in ipi.index:
            continue
        # As known at INSEE's first GDP estimate: month 3 of industrial production is not yet published.
        ipi_rt = ipi[:m2].copy()
        ipi_rt[m3] = ipi[m2] * np.exp(monthly_bt.at[m3, "ridge"] / 100)
        q = quarterly(raw, ipi_rt)
        if q.loc[[t], FEATURES].isna().any(axis=None):
            continue
        preds = fit_predict(training(q, t), q.loc[[t]])
        rows.append({"quarter": t, "actual": q.at[t, "y"], **{k: float(v[0]) for k, v in preds.items()}})
    return pd.DataFrame(rows).set_index("quarter")


def scores(bt: pd.DataFrame) -> dict:
    """Normal quarters (COVID excluded): RMSE, MAE, direction, DM p against AR(1), out-of-sample coverage."""
    normal = bt.drop(COVID, errors="ignore")
    err = normal[list(MODELS)].sub(normal["actual"], axis=0)
    rmse = np.sqrt((err**2).mean())
    dm = lambda m: float(norm.sf(((err["ar"] ** 2 - err[m] ** 2).mean()) / ((err["ar"] ** 2 - err[m] ** 2).std() / np.sqrt(len(err)))))
    q = pd.Series([err["ridge"][err.index < t].abs().quantile(0.8) if (err.index < t).sum() >= 12 else np.nan for t in err.index], index=err.index)
    inside = (err["ridge"].abs() <= q)[q.notna()]
    return {
        "n": int(len(normal)), "from": str(normal.index.min()), "to": str(normal.index.max()),
        "rmse": {k: float(v) for k, v in rmse.items()},
        "mae": {k: float(v) for k, v in err.abs().mean().items()},
        "hit": {k: float((np.sign(normal[k]) == np.sign(normal["actual"])).mean()) for k in MODELS},
        "dm_p": {m: dm(m) for m in ("bridge", "ridge")},
        "q80": float(err["ridge"].abs().quantile(0.8)),
        "coverage": {"share": float(inside.mean()), "n": int(len(inside))},
    }


def nowcast(raw, estimated_ipi: dict[pd.Period, float]) -> tuple[pd.DataFrame, dict]:
    """Quarters INSEE hasn't published whose 3 months are published or estimated by the monthly nowcast.

    Returns the predictions and the ridge model taken apart (as for the monthly model page)."""
    ipi = monthly(raw, "ipi_industry")
    ipi = pd.concat([ipi, pd.Series(estimated_ipi)]).sort_index()
    q = quarterly(raw, ipi)
    pending = q[q["y"].isna()].dropna(subset=FEATURES)
    train = q.drop(COVID, errors="ignore").dropna(subset=["y", *FEATURES])
    preds = pd.DataFrame(fit_predict(train, pending), index=pending.index)
    model = MODELS["ridge"][1]().fit(train[FEATURES], train["y"])
    scaler, ridge = model[0], model[-1]
    z = (pending[FEATURES] - scaler.mean_) / scaler.scale_
    contrib = z * ridge.coef_
    assert np.allclose(ridge.intercept_ + contrib.sum(axis=1), preds["ridge"]), "decomposition differs from the model"
    detail = {
        "alpha": float(ridge.alpha_), "intercept": float(ridge.intercept_),
        "train": {"n": len(train), "from": str(train.index.min()), "to": str(train.index.max())},
        "features": [{"name": c, "mean": float(m), "scale": float(s), "coef": float(w)}
                     for c, m, s, w in zip(FEATURES, scaler.mean_, scaler.scale_, ridge.coef_)],
        "quarters": [{"q": str(t), "x": pending.loc[t, FEATURES].astype(float).tolist(), "contrib": contrib.loc[t].tolist(),
                      "pred": float(preds.at[t, "ridge"])} for t in pending.index],
    }
    return preds, detail


def main() -> None:
    raw = load_raw()
    bt = backtest(raw, pd.read_parquet(DATA / "model" / "backtest.parquet"))
    bt.to_parquet(DATA / "model" / "gdp_backtest.parquet")
    s = scores(bt)
    print(f"GDP bridge, walk-forward {s['from']} to {s['to']} ({s['n']} normal quarters), as known at INSEE's first estimate")
    for k in MODELS:
        print(f"  {k:6} RMSE {s['rmse'][k]:.3f}  MAE {s['mae'][k]:.3f}  direction {s['hit'][k]:.0%}")
    print(f"  vs AR(1), DM p: bridge {s['dm_p']['bridge']:.3f}, ridge {s['dm_p']['ridge']:.3f}")


if __name__ == "__main__":
    main()
