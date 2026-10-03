"""Model variants tested against the published model (D24), shown on the model page.

Run with `uv run experiments` after `uv run backtest`. Writes data/model/experiments.json.
Every variant goes through the same walk-forward backtest as the published model.
"""

import json

import numpy as np
import pandas as pd

from .features import load_raw
from .model import COVID, backtest, scorecard
from .store import DATA

VARIANTS = {
    "published": None,  # expanding fit: what the site publishes
    "recent": {"window_years": 3},
    "holidays": {"holidays": True},
    "both": {"window_years": 3, "holidays": True},
}


def evaluate(bt) -> dict:
    sc = scorecard(bt).loc["excl. Mar-Jul 2020"].loc["ridge"]
    normal = bt.drop(COVID, errors="ignore")
    err = normal["ridge"] - normal["actual"]
    recent = normal.iloc[-24:]
    rmse = lambda c: float(np.sqrt(((recent[c] - recent["actual"]) ** 2).mean()))
    september = err[[m for m in err.index if m.month == 9 and m.year >= 2022]]
    return {
        "rmse": float(sc["rmse"]), "vs_ar": float(sc["rmse_vs_ar"]), "dm_p": float(sc["dm_p_vs_ar"]),
        "hit": float(sc["direction_hit"]), "rmse_last24": rmse("ridge"), "ar_last24": rmse("ar"),
        "sept_bias": float(september.mean()),
    }


def main() -> None:
    raw = load_raw()
    published = DATA / "model" / "backtest.parquet"
    results = {}
    for name, weather in VARIANTS.items():
        bt = pd.read_parquet(published) if weather is None else backtest(raw, weather)
        results[name] = {k: round(v, 4) for k, v in evaluate(bt).items()}
        print(name, results[name], flush=True)
    (DATA / "model" / "experiments.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
