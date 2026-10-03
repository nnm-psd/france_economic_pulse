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
from .model import COVID, MODELS, diagnostics, explain, nowcast, scorecard
from .sources import bodacc, ecb, insee, rte, weather

SITE = Path(__file__).resolve().parent.parent / "site"
LOG = store.DATA / "nowcasts.parquet"  # every published estimate, one row per (day, month)
SINCE = pd.Period("2015-01", "M")  # charts start here


def points(s: pd.Series, digits: int = 2) -> list[dict]:
    s = s.dropna()
    return [{"m": str(p), "v": round(float(v), digits)} for p, v in s.items()]


def expected_release(m: pd.Period) -> str:
    """INSEE's rule: the IPI comes out 35 days after the month ends (40 for July and November).
    ponytail: a weekend date moves to Monday; INSEE's own calendar (insee.fr, 4 months ahead) has the exact day."""
    d = m.end_time.normalize() + pd.Timedelta(days=40 if m.month in (7, 11) else 35)
    return (d + pd.offsets.BDay(0)).date().isoformat()


def log_nowcasts(rows: list[dict]) -> pd.DataFrame:
    """Archive today's published estimates, so each can be scored once INSEE publishes the month."""
    new = pd.DataFrame([{"made": pd.Timestamp(date.today()), "month": r["m"], "g": r["g"], "lo": r["lo"], "hi": r["hi"]} for r in rows])
    log = pd.concat([pd.read_parquet(LOG), new]) if LOG.exists() else new
    log = log.drop_duplicates(["made", "month"], keep="last").sort_values(["made", "month"]).reset_index(drop=True)
    log.to_parquet(LOG, index=False)
    return log


def live_record(log: pd.DataFrame) -> list[dict]:
    """Real-time track record: for each month INSEE has published since estimates started being archived,
    the last estimate made before the release against INSEE's first figure (from the release snapshots, D8)."""
    first: dict[str, tuple[pd.Timestamp, float]] = {}
    for path in sorted((store.DATA / "snapshots" / "ipi").glob("*.parquet")):
        snap = pd.read_parquet(path).query("series == 'ipi_industry'").set_index("date")["value"]
        growth = 100 * np.log(snap).diff()
        growth.index = growth.index.to_period("M")
        for m, g in growth.dropna().items():
            first.setdefault(str(m), (pd.Timestamp(path.stem), float(g)))
    out = []
    for m, (released, actual) in sorted(first.items()):
        before = log[(log["month"] == m) & (log["made"] < released)]
        if before.empty:
            continue
        e = before.iloc[-1]
        out.append({
            "m": m, "made": e["made"].date().isoformat(), "released": released.date().isoformat(),
            "estimate": float(e["g"]), "lo": float(e["lo"]), "hi": float(e["hi"]), "actual": round(actual, 2),
            "error": round(float(e["g"]) - actual, 2), "inside": bool(e["lo"] <= actual <= e["hi"]),
        })
    return out


def last_change(log: pd.DataFrame, month: str) -> dict:
    """When the latest month's estimate last changed, and from what (for the home page)."""
    hist = log[log["month"] == month].sort_values("made").reset_index(drop=True)
    changed = hist.index[hist["g"].ne(hist["g"].shift())]  # rows where the value differs from the day before
    since = hist.loc[changed[-1]]
    before = hist.loc[changed[-1] - 1, "g"] if changed[-1] > 0 else None
    return {"m": month, "now": float(since["g"]), "before": None if before is None else float(before), "since": since["made"].date().isoformat()}


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
            "release": expected_release(m),
        })

    log = log_nowcasts(rows)

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
        "change": last_change(log, rows[-1]["m"]),
        "history": [  # latest archived estimates, newest first, for the RSS feeds
            {"made": r.made.date().isoformat(), "m": r.month, "g": float(r.g)}
            for r in log.sort_values(["made", "month"], ascending=False).head(60).itertuples()
        ],
        "live": live_record(log),
        "track": {
            "from": str(bt.index.min()), "to": str(bt.index.max()), "n": len(normal),
            "rmse": round(sc.at["ridge", "rmse"], 3), "rmse_ar": round(sc.at["ar", "rmse"], 3),
            "ratio": round(sc.at["ridge", "rmse_vs_ar"], 3), "dm_p": round(sc.at["ridge", "dm_p_vs_ar"], 3),
            "hit": round(sc.at["ridge", "direction_hit"], 3),
            "hit_ar": round(sc.at["ar", "direction_hit"], 3),
            "q80": round(q, 2),
        },
        "backtest": [
            {"m": str(m), "actual": round(r.actual, 2), "ridge": round(r.ridge, 2), "ar": round(r.ar, 2), "gbm": round(r.gbm, 2)}
            for m, r in bt.iterrows()
        ],
        # Every model, every metric, for normal months and for all months (D21).
        "scores": {
            period: [{"model": name, **{k: None if pd.isna(v) else round(float(v), 4) for k, v in table.loc[name].items()}} for name in MODELS]
            for period, table in (("normal", scorecard(bt).loc["excl. Mar-Jul 2020"]), ("all", scorecard(bt).loc["all months"]))
        },
        "diagnostics": diagnostics(bt),
        "experiments": json.loads((store.DATA / "model" / "experiments.json").read_text(encoding="utf-8")),  # D24
        "indicators": {
            "electricity": points(elec[SINCE:], 2),
            "climate": points(f["climate"][SINCE:] + 100, 1),
            "insolvencies": points(openings[complete][SINCE:], 0),
            "spread": points(((f["spread_lag1"].shift(-1))[SINCE:]), 0),
        },
        "model": explain(raw),
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
