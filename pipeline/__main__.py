"""Daily update: fetch only new data from each source, check it, store it (D6, D8, D9).

Run with `uv run pipeline`. Exits non-zero if any source fails, after saving the others.
"""

import sys
from datetime import datetime

from . import store
from .sources import bodacc, ecb, gdp, insee, rte, weather

SOURCES = [rte, insee, gdp, ecb, bodacc, weather]


def check(src, new, first_run: bool) -> None:
    assert not (first_run and new.empty), "no data on first run"
    assert set(src.KEY) <= set(new.columns), f"missing key columns {src.KEY}"
    assert not new.isna().any().any(), "null values"
    assert not new.duplicated(src.KEY).any(), "duplicate keys"


def update(src) -> str:
    stored = store.load(src.NAME)
    since = None if stored.empty or src.OVERLAP is None else (stored["date"].max() - src.OVERLAP).date()
    new = src.fetch(since)
    check(src, new, stored.empty)
    added, updated = store.save(src.NAME, new, src.KEY, src.PARTITION)
    if src is insee and store.snapshot("ipi", new[new["series"].isin(insee.TARGET)]):
        print("  ipi: new release archived")
    if src is gdp and store.snapshot("gdp", new):
        print("  gdp: new release archived")
    stored = store.load(src.NAME)
    # With several series, the stalest one decides.
    latest = stored.groupby("series")["date"].max().min() if "series" in stored else stored["date"].max()
    assert datetime.now() - latest <= src.MAX_AGE, f"stale: latest point {latest:%Y-%m-%d}"
    return f"fetched {len(new)} rows since {since or 'start'}, {added} added, {updated} updated, latest {latest:%Y-%m-%d %H:%M}"


def main() -> None:
    failed = []
    for src in SOURCES:
        try:
            print(f"{src.NAME}: {update(src)}")
        except Exception as e:
            print(f"{src.NAME}: FAILED: {e!r}")
            failed.append(src.NAME)
    sys.exit(f"failed: {', '.join(failed)}" if failed else 0)


if __name__ == "__main__":
    main()
