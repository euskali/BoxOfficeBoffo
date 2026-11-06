from __future__ import annotations

from pathlib import Path

import pytest

from boffo_etl.manual import SCHEMAS

REAL_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    """A temporary repo root with header-only manual CSVs; BOFFO_FETCH and BOFFO_REQUIRE_DATA unset."""
    monkeypatch.setenv("BOFFO_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("BOFFO_FETCH", raising=False)
    monkeypatch.delenv("BOFFO_REQUIRE_DATA", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    manual = tmp_path / "data" / "manual"
    manual.mkdir(parents=True)
    for name, schema in SCHEMAS.items():
        (manual / name).write_text(",".join(schema.columns) + "\n", encoding="utf-8")
    return tmp_path
