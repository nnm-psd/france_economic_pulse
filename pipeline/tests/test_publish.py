import numpy as np
import pandas as pd

from pipeline import publish, store


def snapshot(path, values: dict[str, float]):
    pd.DataFrame({
        "date": pd.to_datetime(list(values)), "series": "ipi_industry", "value": list(values.values()),
    }).to_parquet(path, index=False)


def test_live_record_scores_the_last_estimate_made_before_the_release(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    snaps = tmp_path / "snapshots" / "ipi"
    snaps.mkdir(parents=True)
    snapshot(snaps / "2026-10-02.parquet", {"2026-06-01": 100.0, "2026-07-01": 101.0})
    snapshot(snaps / "2026-10-10.parquet", {"2026-06-01": 100.0, "2026-07-01": 101.0, "2026-08-01": 102.0})
    log = pd.DataFrame({
        "made": pd.to_datetime(["2026-10-03", "2026-10-05", "2026-10-10"]),
        "month": "2026-08",
        "g": [0.35, 0.50, 9.0],  # the 10-10 estimate was made on release day: must not count
        "lo": [-1.3, -1.2, 8.0],
        "hi": [2.0, 2.2, 10.0],
    })
    [r] = publish.live_record(log)  # July has no archived estimate, so only August is scored
    actual = 100 * np.log(102 / 101)
    assert (r["m"], r["made"], r["released"], r["estimate"]) == ("2026-08", "2026-10-05", "2026-10-10", 0.50)
    assert r["actual"] == round(actual, 2) and r["inside"]


def test_last_change_reports_the_latest_revision():
    log = pd.DataFrame({
        "made": pd.to_datetime(["2026-10-03", "2026-10-04", "2026-10-05", "2026-10-06"]),
        "month": "2026-09", "g": [-0.44, -0.44, -0.30, -0.30], "lo": 0.0, "hi": 0.0,
    })
    assert publish.last_change(log, "2026-09") == {"m": "2026-09", "now": -0.30, "before": -0.44, "since": "2026-10-05"}


def test_expected_release_follows_insee_rule():
    assert publish.expected_release(pd.Period("2026-07", "M")) == "2026-09-09"  # 40 days: the actual July release
    assert publish.expected_release(pd.Period("2026-08", "M")) == "2026-10-05"  # 35 days
    assert publish.expected_release(pd.Period("2026-02", "M")) == "2026-04-06"  # 4 April is a Saturday: Monday


def test_evolution_splits_each_change_into_news_and_reestimation_exactly():
    from pipeline.features import FEATURES

    days = pd.to_datetime(["2026-10-03", "2026-10-04"])
    x0 = {f"x_{c}": 1.0 for c in FEATURES}
    x1 = {**x0, "x_elec": 3.0}  # new electricity data on day 2
    log = pd.DataFrame([
        {"made": days[0], "month": "2026-09", "g": -0.44, "lo": -2.0, "hi": 1.0, "pred": -0.44, **x0},
        {"made": days[1], "month": "2026-09", "g": -0.10, "lo": -1.7, "hi": 1.4, "pred": -0.10, **x1},
    ])
    params = pd.DataFrame([{"made": d, "intercept": 0.0, **{f"{k}_{c}": v for c in FEATURES for k, v in
                           (("mean", 0.0), ("scale", 2.0), ("coef", 0.25))}} for d in days])
    [month] = publish.evolution(log, params, [])
    [change] = month["changes"]
    assert change["news"]["electricity"] == 0.25 * (3.0 - 1.0) / 2.0  # weight * change / scale = 0.25
    assert abs(change["total"] - (sum(change["news"].values()) + change["refit"])) < 1e-9
    assert change["refit"] == round(0.34 - 0.25, 3)  # the rest of the +0.34 move
