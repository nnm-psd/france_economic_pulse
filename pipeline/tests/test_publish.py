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
