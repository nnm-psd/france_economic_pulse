"""Write the website's data file (D15).

Run with `uv run publish` after `uv run backtest`. Writes site/src/data/site.json (imported by the
pages at build time) and site/public/data/site.json (the same file, offered as a download).
The JSON holds codes, ISO months and numbers only; all labels live in the site (D19).
"""

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import store
from .features import corrected_electricity, daily_electricity, load_raw, monthly_features
from .model import COVID, nowcast, scorecard
from .sources import bodacc, ecb, insee, rte, weather

SITE = Path(__file__).resolve().parent.parent / "site"
SINCE = pd.Period("2015-01", "M")  # charts start here


def points(s: pd.Series, digits: int = 2) -> list[dict]:
    s = s.dropna()
    return [{"m": str(p), "v": round(float(v), digits)} for p, v in s.items()]


def build() -> dict:
    raw = load_raw()
    f = monthly_features(raw, fit_until=pd.Timestamp.now())
    ipi = raw["insee"].query("series == 'ipi_industry'").set_index("date")["value"]
    ipi.index = ipi.index.to_period("M")
    last = ipi.index.max()

    # Uncertainty from past errors: 80% of normal-month misses were within ±q (D21).
    bt = pd.read_parquet(store.DATA / "model" / "backtest.parquet")
    normal = bt.drop(COVID, errors="ignore")
    q = float((normal["ridge"] - normal["actual"]).abs().quantile(0.8))
    sc = scorecard(bt).loc["excl. Mar-Jul 2020"]

    # ponytail: the two-month-ahead band widens by sqrt(2), assuming independent monthly errors.
    level, rows = float(ipi[last]), []
    for i, (m, g) in enumerate(nowcast(raw)["ridge"].items(), start=1):
        level *= np.exp(g / 100)
        spread = q * np.sqrt(i)
        rows.append({
            "m": str(m), "g": round(float(g), 2), "lo": round(float(g) - q, 2), "hi": round(float(g) + q, 2),
            "level": round(level, 2),
            "level_lo": round(level * np.exp(-spread / 100), 2), "level_hi": round(level * np.exp(spread / 100), 2),
            "release": str(m + 2),  # INSEE publishes early in month m+2
        })

    elec = corrected_electricity(daily_electricity(raw["rte"]), raw["weather"].set_index("date")["temp_c"], pd.Timestamp.now())
    elec = 100 * np.exp(elec - elec[pd.period_range("2019-01", "2019-12", freq="M")].mean())
    openings = raw["bodacc"].set_index("date")["openings"]
    openings = openings.groupby(openings.index.to_period("M")).sum()
    complete = openings.index < pd.Period(date.today(), "M")  # drop the month in progress

    sources = {s.NAME: s for s in (rte, insee, ecb, bodacc, weather)}
    return {
        "generated": date.today().isoformat(),
        "ipi": points(ipi[SINCE:]),
        "last_official": {"m": str(last), "v": round(float(ipi[last]), 2), "g": round(float(f.at[last, "y"]), 2)},
        "nowcast": rows,
        "track": {
            "from": str(bt.index.min()), "to": str(bt.index.max()), "n": len(normal),
            "rmse": round(sc.at["ridge", "rmse"], 3), "rmse_ar": round(sc.at["ar", "rmse"], 3),
            "ratio": round(sc.at["ridge", "rmse_vs_ar"], 3), "dm_p": round(sc.at["ridge", "dm_p_vs_ar"], 3),
            "hit": round(sc.at["ridge", "direction_hit"], 3),
            "hit_ar": round(sc.at["ar", "direction_hit"], 3),
            "q80": round(q, 2),
        },
        "backtest": [
            {"m": str(m), "actual": round(r.actual, 2), "ridge": round(r.ridge, 2), "ar": round(r.ar, 2)}
            for m, r in bt.iterrows()
        ],
        "indicators": {
            "electricity": points(elec[SINCE:], 2),
            "climate": points(f["climate"][SINCE:] + 100, 1),
            "insolvencies": points(openings[complete][SINCE:], 0),
            "spread": points(((f["spread_lag1"].shift(-1))[SINCE:]), 0),
        },
        "sources": [
            {"id": name, "latest": store.load(name)["date"].max().date().isoformat(), "max_age_days": s.MAX_AGE.days}
            for name, s in sources.items()
        ],
    }


def main() -> None:
    text = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    for path in (SITE / "src" / "data" / "site.json", SITE / "public" / "data" / "site.json"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(f"wrote site data ({len(text) // 1024} KB)")


if __name__ == "__main__":
    main()
