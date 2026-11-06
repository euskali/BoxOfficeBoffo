from __future__ import annotations

import json
from datetime import datetime

from boffo_etl import build


def test_build_creates_dirs_and_manifest(repo, capsys):
    assert build.main([]) == 0
    for d in ("data/raw", "data/build", "site/public/data"):
        assert (repo / d).is_dir()
    m = json.loads((repo / "site/public/data/manifest.json").read_text())
    assert m["schema_version"] == 1
    assert m["tables"] == []
    assert m["git_sha"] is None
    datetime.fromisoformat(m["built_at"])
    out = capsys.readouterr().out
    assert "disabled" in out and "not implemented until M1" in out


def test_build_records_git_sha_and_fetch_flag(repo, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    monkeypatch.setenv("BOFFO_FETCH", "1")
    assert build.main([]) == 0
    assert json.loads((repo / "site/public/data/manifest.json").read_text())["git_sha"] == "abc123"
    assert "ENABLED" in capsys.readouterr().out


def test_build_aborts_on_manual_errors(repo, capsys):
    (repo / "data/manual/ticket_prices.csv").write_text("bad,header\n", encoding="utf-8")
    assert build.main([]) == 1
    assert not (repo / "site/public/data/manifest.json").exists()
