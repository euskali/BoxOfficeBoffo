"""Build orchestrator. Run with ``python -m boffo_etl.build``."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import polars as pl

from . import paths
from .fetch import FetchDisabledError
from .manual import validate_manual_dir
from .sources import stat695

REQUIRE_DATA_FLAG = "BOFFO_REQUIRE_DATA"

# Source steps: (name, milestone, callable or None if not implemented yet).
# Each step writes its per-source tables to data/build/.
STEPS: list[tuple[str, str, Callable[[], object] | None]] = [
    ("stat695", "M1", stat695.run),
    ("bom_weekend", "M2", None),
    ("wikidata", "M3/M4", None),
    ("cpi", "M5", None),
]

# Shipped tables and the per-source parts in data/build/ they are combined from.
SNAPSHOT_SOURCES = ("stat695", "bom_weekend")
PUBLISHED = ("snapshots", "releases")


def _table_entry(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "name": path.stem,
        "file": path.name,
        "rows": pl.scan_parquet(path).select(pl.len()).collect().item(),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def publish_tables() -> list[dict]:
    """Combine per-source parts into site/public/data/<table>.parquet."""
    tables = []
    for table in PUBLISHED:
        parts = [paths.data_build() / f"{src}_{table}.parquet" for src in SNAPSHOT_SOURCES]
        parts = [p for p in parts if p.is_file()]
        if not parts:
            continue
        out = paths.site_data() / f"{table}.parquet"
        pl.concat([pl.read_parquet(p) for p in parts], how="diagonal_relaxed").write_parquet(out)
        tables.append(_table_entry(out))
    return tables


def write_manifest(tables: list | None = None) -> None:
    manifest = {
        "schema_version": 1,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": os.environ.get("GITHUB_SHA") or None,
        "tables": tables or [],
    }
    out = paths.site_data() / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    for d in (paths.data_raw(), paths.data_build(), paths.site_data()):
        d.mkdir(parents=True, exist_ok=True)

    issues = validate_manual_dir(paths.data_manual())
    for issue in issues:
        print(issue)
    if any(i.severity == "error" for i in issues):
        print("build aborted: fix manual CSV errors first", file=sys.stderr)
        return 1

    fetch_on = os.environ.get("BOFFO_FETCH") == "1"
    require = os.environ.get(REQUIRE_DATA_FLAG) == "1"
    print(f"network fetching: {'ENABLED (BOFFO_FETCH=1)' if fetch_on else 'disabled (set BOFFO_FETCH=1 in CI to enable)'}")

    for name, milestone, step in STEPS:
        if step is None:
            print(f"step {name}: skipped, not implemented until {milestone}")
            continue
        print(f"step {name}: running")
        try:
            step()
        except FetchDisabledError as exc:
            if require:
                print(f"step {name}: FAILED, {REQUIRE_DATA_FLAG}=1 and {exc}", file=sys.stderr)
                return 1
            print(f"step {name}: skipped, its raw input is not cached in data/raw/ (data is fetched in CI)")

    tables = publish_tables()
    for t in tables:
        print(f"published {t['file']}: {t['rows']} rows")
    write_manifest(tables)
    print(f"wrote {paths.site_data() / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
