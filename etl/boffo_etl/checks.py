"""Data-quality report. Run with ``python -m boffo_etl.checks``; exits 1 on any error."""

from __future__ import annotations

import sys
from typing import Callable

from . import paths
from .manual import Issue, validate_manual_dir


def check_manual() -> list[Issue]:
    return validate_manual_dir(paths.data_manual())


def _parquet_files() -> list:
    found = []
    for directory in (paths.data_build(), paths.site_data()):
        if directory.is_dir():
            found.extend(sorted(directory.rglob("*.parquet")))
    return found


def check_built_tables() -> list[Issue]:
    """List built Parquet tables with row counts. Absence is not an error."""
    files = _parquet_files()
    if not files:
        print("Built tables: no built tables yet (data is built in CI)")
        return []
    import duckdb

    issues: list[Issue] = []
    con = duckdb.connect()  # private connection; never touch the global default one
    print("Built tables:")
    root = paths.repo_root()
    for f in files:
        rel = f.relative_to(root).as_posix() if f.is_relative_to(root) else str(f)
        try:
            n = con.execute("SELECT count(*) FROM read_parquet(?)", [str(f)]).fetchall()[0][0]
            print(f"  {rel}: {n} rows")
        except Exception as exc:  # unreadable parquet is a real problem
            issues.append(Issue("error", rel, 0, f"cannot read parquet: {exc}"))
    con.close()
    return issues


# ---------------------------------------------------------------------------
# EXTENSION POINT: M1+ data checks plug in here.
# Each check is a zero-argument callable returning a list of Issue. Add new
# checks to CHECKS (e.g. decreasing cumulative totals per release, duplicate
# ranks within a weekend, weekend gaps). Checks must flag anomalies, never
# silently fix them.
# ---------------------------------------------------------------------------
CHECKS: list[Callable[[], list[Issue]]] = [
    check_manual,
    check_built_tables,
]


def main(argv: list[str] | None = None) -> int:
    issues: list[Issue] = []
    for check in CHECKS:
        issues.extend(check())
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    print()
    for issue in issues:
        print(issue)
    print(f"\nchecks: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
