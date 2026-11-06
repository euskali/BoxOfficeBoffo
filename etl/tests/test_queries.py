"""One SQL source of truth: the site's query files are executed here with duckdb."""

from __future__ import annotations

import duckdb
import pytest

from conftest import REAL_REPO_ROOT

QUERIES = REAL_REPO_ROOT / "site" / "src" / "queries"


def test_queries_dir_has_sql():
    assert list(QUERIES.glob("*.sql"))


@pytest.mark.parametrize("path", sorted(QUERIES.glob("*.sql")), ids=lambda p: p.name)
def test_sql_files_readable(path):
    assert path.read_text(encoding="utf-8").strip()


def test_hello_query_executes():
    sql = (QUERIES / "hello.sql").read_text(encoding="utf-8")
    con = duckdb.connect()
    rows = con.execute(sql).fetchall()
    con.close()
    assert rows[0][0] == 1999
