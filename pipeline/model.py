"""Nowcast models and walk-forward backtest (D10, D11).

Run with `uv run backtest`. Writes data/model/backtest.parquet and prints the scorecard
and the nowcast for months INSEE has not published yet.
"""

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import FEATURES, load_raw, monthly_features
from .store import DATA

START = pd.Period("2016-01", "M")  # first backtest month: ~4 years of training data before it
COVID = pd.period_range("2020-03", "2020-07", freq="M")

MODELS = {
    "ar": (["y_lag2"], LinearRegression),
    "ridge": (FEATURES, lambda: make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 30)))),
    "gbm": (FEATURES, lambda: HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, random_state=0)),
}


def training_rows(f: pd.DataFrame, t: pd.Period) -> pd.DataFrame:
    """Months whose IPI was already published when nowcasting t (up to t-2), with complete features.

    COVID months are left out of training (still scored in the backtest): a 25% collapse and
    rebound teaches the models relationships that do not hold in normal months.
    """
    return f.loc[: t - 2].drop(COVID, errors="ignore").dropna(subset=["y", *FEATURES])


def predict(f: pd.DataFrame, train: pd.DataFrame, target: pd.DataFrame) -> dict[str, np.ndarray]:
    out = {}
    for name, (cols, make) in MODELS.items():
        out[name] = make().fit(train[cols], train["y"]).predict(target[cols])
    return out


def backtest(raw) -> pd.DataFrame:
    """Expanding window: for each month t, refit everything on data available at the start of t+1."""
    last = raw["insee"].query("series == 'ipi_industry'")["date"].max().to_period("M")
    rows = []
    for t in pd.period_range(START, last, freq="M"):
        f = monthly_features(raw, fit_until=(t + 1).start_time)
        if f.loc[[t], FEATURES].isna().any(axis=None):
            continue
        preds = predict(f, training_rows(f, t), f.loc[[t]])
        rows.append({"month": t, "actual": f.at[t, "y"], **{k: v[0] for k, v in preds.items()}})
    return pd.DataFrame(rows).set_index("month")


def scorecard(bt: pd.DataFrame) -> pd.DataFrame:
    def score(df):
        err = df[list(MODELS)].sub(df["actual"], axis=0)
        rmse = np.sqrt((err**2).mean())
        # Diebold-Mariano: is the squared-error gain over AR(1) larger than chance? (one-sided p-value)
        d = (err**2).rsub((err["ar"] ** 2), axis=0)
        dm_p = pd.Series(norm.sf(d.mean() / (d.std() / np.sqrt(len(d)))), index=d.columns)
        return pd.DataFrame({
            "rmse": rmse,
            "rmse_vs_ar": rmse / rmse["ar"],
            "dm_p_vs_ar": dm_p.where(d.std() > 0),
            "direction_hit": df[list(MODELS)].apply(lambda p: (np.sign(p) == np.sign(df["actual"])).mean()),
        })
    return pd.concat({"all months": score(bt), "excl. Mar-Jul 2020": score(bt.drop(COVID, errors="ignore"))})


def nowcast(raw) -> pd.DataFrame:
    """Models refitted on everything published, applied to months with features but no IPI yet."""
    f = monthly_features(raw, fit_until=pd.Timestamp.now())
    pending = f[f["y"].isna()].dropna(subset=FEATURES)
    train = f.drop(COVID).dropna(subset=["y", *FEATURES])
    return pd.DataFrame(predict(f, train, pending), index=pending.index)


def main() -> None:
    raw = load_raw()
    bt = backtest(raw)
    (DATA / "model").mkdir(exist_ok=True)
    bt.to_parquet(DATA / "model" / "backtest.parquet")
    pd.set_option("display.precision", 3)
    print(f"Walk-forward backtest, {bt.index.min()} to {bt.index.max()} ({len(bt)} months),")
    print("target: monthly growth of industrial production (%), revised data (optimistic, see D8)\n")
    print(scorecard(bt), "\n")
    print("Nowcast for unpublished months (% growth):")
    print(nowcast(raw))


if __name__ == "__main__":
    main()
