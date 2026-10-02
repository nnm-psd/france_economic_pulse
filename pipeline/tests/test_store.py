import pandas as pd

from pipeline import store


def frame(rows):
    return pd.DataFrame(rows, columns=["date", "value"]).assign(date=lambda d: pd.to_datetime(d["date"]))


def test_second_run_only_adds_new_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    first = frame([("2026-08-31", 1.0), ("2026-09-01", 2.0)])
    assert store.save("s", first, ["date"]) == (2, 0)
    assert sorted(p.name for p in (tmp_path / "raw" / "s").iterdir()) == ["2026-08.parquet", "2026-09.parquet"]

    # Same data again: nothing added, nothing rewritten.
    mtime = (tmp_path / "raw" / "s" / "2026-08.parquet").stat().st_mtime_ns
    assert store.save("s", first, ["date"]) == (0, 0)
    assert (tmp_path / "raw" / "s" / "2026-08.parquet").stat().st_mtime_ns == mtime

    # Overlapping fetch: one revised value, one new row.
    assert store.save("s", frame([("2026-09-01", 2.5), ("2026-09-02", 3.0)]), ["date"]) == (1, 1)
    assert store.load("s")["value"].tolist() == [1.0, 2.5, 3.0]


def test_snapshot_only_when_release_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    release = frame([("2026-07-01", 102.95)])
    assert store.snapshot("ipi", release)
    assert not store.snapshot("ipi", release)
