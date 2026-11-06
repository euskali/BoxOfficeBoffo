from __future__ import annotations

import json
from datetime import date, timedelta

import polars as pl
import pytest

from boffo_etl import checks
from boffo_etl.sources.stat695 import RELEASE_SCHEMA, SNAPSHOT_SCHEMA


def test_clean_repo_exits_zero(repo, capsys):
    assert checks.main([]) == 0
    assert "no built tables yet (data is built in CI)" in capsys.readouterr().out


def test_invalid_manual_csv_exits_one(repo, capsys):
    (repo / "data" / "manual" / "ticket_prices.csv").write_text(
        "year,avg_price_usd,source,source_url,notes\n1990,4.2,TODO,,\n", encoding="utf-8"
    )
    assert checks.main([]) == 1
    assert "placeholder" in capsys.readouterr().out


def test_lists_parquet_row_counts(repo, capsys):
    out = repo / "data" / "build"
    out.mkdir(parents=True)
    pl.DataFrame({"a": [1, 2, 3]}).write_parquet(out / "t.parquet")
    assert checks.main([]) == 0
    assert "t.parquet: 3 rows" in capsys.readouterr().out


# --- snapshots / releases ----------------------------------------------------

SUN = date(1990, 1, 7)  # a Sunday


def snap(week: int, release: str, rank: int, total: int, weekend: int = 100, end: date | None = None) -> dict:
    return {
        "weekend_end": end or SUN + timedelta(weeks=week), "release_id": f"legacy:{release}",
        "title_id": f"bb_{release}", "rank": rank, "weekend_gross": weekend, "theaters": 10,
        "total_gross": total, "weeks": week + 1, "source": "stat695", "capture_url": None, "is_estimate": False,
    }


def write_tables(repo, snaps: list[dict], releases: list[str] | None = None) -> None:
    site = repo / "site" / "public" / "data"
    site.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(snaps, schema=SNAPSHOT_SCHEMA).write_parquet(site / "snapshots.parquet")
    ids = releases if releases is not None else sorted({s["release_id"].split(":")[1] for s in snaps})
    pl.DataFrame(
        [{"release_id": f"legacy:{r}", "title_id": f"bb_{r}", "source_key": r, "source": "stat695",
          "is_rerelease": False, "group_source": "auto"} for r in ids],
        schema=RELEASE_SCHEMA,
    ).write_parquet(site / "releases.parquet")


def run(capsys) -> tuple[int, str]:
    code = checks.main([])
    return code, capsys.readouterr().out


CLEAN = [snap(0, "a", 1, 100), snap(0, "b", 2, 50, weekend=50), snap(1, "a", 1, 200), snap(1, "b", 2, 80, weekend=30)]


def test_clean_snapshots_pass(repo, capsys):
    write_tables(repo, CLEAN)
    code, out = run(capsys)
    assert code == 0, out
    assert "snapshots: 2 weekends from 1990-01-07 to 1990-01-14, 0 missing" in out
    assert "0 error(s), 0 warning(s)" in out


def test_duplicate_ranks_are_errors(repo, capsys):
    write_tables(repo, CLEAN + [snap(1, "c", 2, 10, weekend=10)])
    code, out = run(capsys)
    assert code == 1
    assert "1 weekends have duplicate ranks" in out and "1990-01-14 rank 2: legacy:b, legacy:c" in out


def test_duplicate_keys_are_errors(repo, capsys):
    write_tables(repo, CLEAN + [snap(1, "a", 3, 200)])
    code, out = run(capsys)
    assert code == 1 and "(weekend_end, release_id) pairs appear more than once" in out


def test_decreasing_totals_are_warnings(repo, capsys):
    write_tables(repo, CLEAN + [snap(2, "a", 1, 150)])
    code, out = run(capsys)
    assert code == 0
    assert "total_gross goes down 1 times in 1 releases (flagged, not fixed)" in out
    assert "legacy:a 1990-01-21: 200 -> 150" in out


def test_total_below_weekend_warns(repo, capsys):
    write_tables(repo, [snap(0, "a", 1, 50, weekend=100)])
    code, out = run(capsys)
    assert code == 0 and "total_gross below weekend_gross" in out


def test_gaps_and_non_sunday_weekends(repo, capsys):
    rows = [
        snap(0, "a", 1, 100),
        snap(3, "a", 1, 300),  # weeks 1 and 2 missing
        snap(0, "b", 1, 100, end=SUN + timedelta(weeks=4, days=1)),  # holiday Monday counts for its Sunday
        snap(0, "b", 1, 200, end=SUN + timedelta(weeks=5)),
    ]
    write_tables(repo, rows)
    code, out = run(capsys)
    assert code == 0
    assert "2 weekends have no chart (gap report)" in out
    assert "weekend ending 1990-01-14; weekend ending 1990-01-21" in out
    assert "1 weekends don't end on a Sunday, e.g. 1990-02-05 (Monday)" in out


def test_release_integrity_errors(repo, capsys):
    write_tables(repo, CLEAN, releases=["a", "a", "BAD"])
    code, out = run(capsys)
    assert code == 1
    assert "1 release_ids appear more than once" in out
    assert "invalid title_id" in out and "bb_BAD" in out
    assert "snapshot release_ids are missing from releases, e.g. legacy:b" in out


# --- stat695 report ------------------------------------------------------------

def report(**kw) -> dict:
    base = {
        "source_rows": 10, "source_releases": 3, "documented_rows": 10, "documented_releases": 3,
        "snapshot_rows": 8, "exact_duplicates_dropped": 1, "unkeyed_rows": 1,
        "unkeyed_examples": [{"_row": 4, "movie_id": "x", "weekend_end": None}],
        "duplicate_chart_labels": [{"chart": "1989W53", "same_as": "1990W01", "rows": 1}],
        "releases": 3, "weekends": 2, "weekend_min": "1990-01-07", "weekend_max": "1990-01-14",
        "nonintegral_values": {}, "nulls": {}, "releases_missing_release_date": 0,
        "releases_with_varying": {}, "rereleases": {}, "manual_groups_applied": 0,
    }
    base.update(kw)
    return base


def write_report(repo, r: dict) -> None:
    build = repo / "data" / "build"
    build.mkdir(parents=True, exist_ok=True)
    (build / "stat695_report.json").write_text(json.dumps(r), encoding="utf-8")


def test_report_flags_source_anomalies(repo, capsys):
    write_report(repo, report())
    code, out = run(capsys)
    assert code == 0
    assert "1 source rows exactly repeat another row" in out and "1989W53 repeats 1990W01" in out
    assert "1 source rows have no end_date or movie_id" in out


@pytest.mark.parametrize("kw, message", [
    ({"snapshot_rows": 9}, "row counts don't reconcile"),
])
def test_report_reconciliation_errors(repo, capsys, kw, message):
    write_report(repo, report(**kw))
    code, out = run(capsys)
    assert code == 1 and message in out


def test_report_documented_counts_warn(repo, capsys):
    write_report(repo, report(documented_rows=11))
    code, out = run(capsys)
    assert code == 0 and "its docs say 11" in out


def test_report_row_count_must_match_parquet(repo, capsys):
    write_report(repo, report())
    pl.DataFrame({"a": [1, 2]}).write_parquet(repo / "data" / "build" / "stat695_snapshots.parquet")
    code, out = run(capsys)
    assert code == 1 and "stat695_snapshots.parquet has 2 rows, the report says 8" in out


def test_report_warns_on_encoding_fallback(repo, capsys):
    write_report(repo, report(unmarked_string_encoding="WINDOWS-1252"))
    code, out = run(capsys)
    assert code == 0 and "read as WINDOWS-1252" in out
