"""Parquet storage: data/raw/<source>/<partition>.parquet (D7).

Each source picks its partition: monthly for large daily-updated data, yearly for small
daily data, a single file for small series that are fully re-fetched anyway.
"""

from datetime import date
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"


def load(source: str) -> pd.DataFrame:
    files = sorted((DATA / "raw" / source).glob("*.parquet"))
    return pd.concat(map(pd.read_parquet, files), ignore_index=True) if files else pd.DataFrame()


def save(source: str, new: pd.DataFrame, key: list[str], partition: str | None = "%Y-%m") -> tuple[int, int]:
    """Merge `new` into the partition files; new values win on duplicate keys.

    `partition` is a strftime pattern for the file name, or None for a single file.
    Only files that actually changed are rewritten, so git diffs stay small.
    Returns (rows added, rows updated).
    """
    folder = DATA / "raw" / source
    folder.mkdir(parents=True, exist_ok=True)
    added = updated = 0
    parts = new["date"].dt.strftime(partition) if partition else pd.Series("all", index=new.index)
    for part, rows in new.groupby(parts):
        path = folder / f"{part}.parquet"
        old = pd.read_parquet(path) if path.exists() else rows.iloc[:0]
        values = [c for c in rows.columns if c not in key]
        m = rows.merge(old, on=key, how="left", suffixes=("", "_old"), indicator=True)
        is_new = m["_merge"] == "left_only"
        changed = ~is_new & (m[values].to_numpy() != m[[f"{c}_old" for c in values]].to_numpy()).any(axis=1)
        if is_new.any() or changed.any():
            merged = pd.concat([old, rows]).drop_duplicates(key, keep="last").sort_values(key)
            merged.reset_index(drop=True).to_parquet(path, index=False)
        added += int(is_new.sum())
        updated += int(changed.sum())
    return added, updated


def snapshot(name: str, df: pd.DataFrame) -> bool:
    """Archive a full release as published, if it differs from the last archive (D8)."""
    folder = DATA / "snapshots" / name
    folder.mkdir(parents=True, exist_ok=True)
    df = df.reset_index(drop=True)
    previous = sorted(folder.glob("*.parquet"))
    if previous and pd.read_parquet(previous[-1]).equals(df):
        return False
    df.to_parquet(folder / f"{date.today():%Y-%m-%d}.parquet", index=False)
    return True
