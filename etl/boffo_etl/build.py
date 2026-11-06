"""Build orchestrator. Run with ``python -m boffo_etl.build``."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Callable

from . import paths
from .manual import validate_manual_dir

# Source steps. Each entry: (name, milestone, callable or None if not implemented yet).
# Add real step functions here as milestones land (M1 stat695, M2 bom_weekend, ...).
STEPS: list[tuple[str, str, Callable[[], None] | None]] = [
    ("stat695", "M1", None),
    ("bom_weekend", "M2", None),
    ("wikidata", "M3/M4", None),
    ("cpi", "M5", None),
]


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
    print(f"network fetching: {'ENABLED (BOFFO_FETCH=1)' if fetch_on else 'disabled (set BOFFO_FETCH=1 in CI to enable)'}")

    for name, milestone, step in STEPS:
        if step is None:
            print(f"step {name}: skipped, not implemented until {milestone}")
        else:
            print(f"step {name}: running")
            step()

    write_manifest()
    print(f"wrote {paths.site_data() / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
