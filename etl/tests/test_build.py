from __future__ import annotations

import json
from datetime import datetime

import polars as pl

from boffo_etl import build
from boffo_etl.fetch import Fetcher
from boffo_etl.sources import stat695
from boffo_etl.sources.stat695 import git_blob_sha1

from test_stat695 import write_fixture_rda


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
    assert "disabled" in out
    assert "step stat695: skipped, its raw input is not cached" in out
    assert "not implemented until M2" in out


def test_build_fails_when_data_is_required(repo, monkeypatch, capsys):
    monkeypatch.setenv("BOFFO_REQUIRE_DATA", "1")
    assert build.main([]) == 1
    assert "FAILED" in capsys.readouterr().err


def test_build_records_git_sha_and_fetch_flag(repo, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    monkeypatch.setenv("BOFFO_FETCH", "1")
    monkeypatch.setattr(build, "STEPS", [("stat695", "M1", lambda: None)])  # never touch the network
    assert build.main([]) == 0
    assert json.loads((repo / "site/public/data/manifest.json").read_text())["git_sha"] == "abc123"
    assert "ENABLED" in capsys.readouterr().out


def test_build_aborts_on_manual_errors(repo, capsys):
    (repo / "data/manual/ticket_prices.csv").write_text("bad,header\n", encoding="utf-8")
    assert build.main([]) == 1
    assert not (repo / "site/public/data/manifest.json").exists()


def test_full_build_from_cached_rda(repo, monkeypatch, capsys):
    """Offline build from a synthetic mojo.rda already in the raw cache."""
    directory, digest = Fetcher._stem(stat695.URL)
    directory.mkdir(parents=True)
    path = write_fixture_rda(directory / f"{digest}.rda")
    monkeypatch.setattr(stat695, "BLOB_SHA1", git_blob_sha1(path.read_bytes()))

    assert build.main([]) == 0
    out = capsys.readouterr().out
    assert "stat695: 4 source rows -> 4 snapshots" in out
    assert "published snapshots.parquet: 4 rows" in out

    site = repo / "site/public/data"
    snaps = pl.read_parquet(site / "snapshots.parquet")
    assert snaps.height == 4 and set(snaps["source"]) == {"stat695"}
    assert pl.read_parquet(site / "releases.parquet").height == 2
    tables = {t["name"]: t for t in json.loads((site / "manifest.json").read_text())["tables"]}
    assert set(tables) == {"snapshots", "releases"}
    assert tables["snapshots"]["rows"] == 4 and len(tables["snapshots"]["sha256"]) == 64
    for f in ("stat695_snapshots.parquet", "stat695_releases.parquet", "stat695_report.json", "stat695_rereleases.csv"):
        assert (repo / "data/build" / f).is_file()
