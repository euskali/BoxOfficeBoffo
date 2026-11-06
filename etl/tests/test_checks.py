from __future__ import annotations

import polars as pl

from boffo_etl import checks


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
