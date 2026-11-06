"""stat695 ingest, tested on tiny synthetic fixtures (never the real mojo.rda).

Titles and figures are invented. The fixture .rda is written by rda_writer with
the same R types the real file uses: a tibble of doubles, factors, an ordered
factor and Date columns.
"""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from boffo_etl.fetch import Fetcher, FetchDisabledError
from boffo_etl.manual import TITLE_ID_RE
from boffo_etl.sources import stat695
from boffo_etl.sources.stat695 import (
    detect_rereleases,
    git_blob_sha1,
    normalize,
    normalize_title,
    provisional_title_ids,
    split_title,
)

from rda_writer import Dates, Doubles, Factor, write_rda

MPAA_LEVELS = ["G", "PG", "PG-13", "NC-17", "R", "Unrated", "Unknown", "Not Yet Rated"]

# One synthetic chart row per tuple:
# (year, week, end_date, rank, movie_id, title, weekend_gross, theaters, total_gross, week_num, release_date)
ROWS = [
    (1983, 1, date(1983, 1, 9), 1, "moonllama", "Moon Llama", 900_000, 400, 900_000, 1, date(1983, 1, 7)),
    (1983, 1, date(1983, 1, 9), 2, "robotpicnic", "Robot Picnic", 500_000, None, 2_500_000, 3, date(1982, 12, 17)),
    (1983, 2, date(1983, 1, 16), 1, "moonllama", "Moon Llama", 700_000, 410, 1_600_000, 2, date(1983, 1, 7)),
    (1983, 2, date(1983, 1, 16), 2, "robotpicnic", "Robot Picnic", 300_000, None, 2_800_000, 4, date(1982, 12, 17)),
]


def frame(rows=ROWS, **overrides) -> pl.DataFrame:
    """The raw data frame as pyreadr returns it: doubles, Enum factors, Dates."""
    cols = list(zip(*rows))
    df = pl.DataFrame(
        {
            "year": [float(v) for v in cols[0]],
            "week": [float(v) for v in cols[1]],
            "rank_this_week": [None if v is None else float(v) for v in cols[3]],
            "title": pl.Series(cols[5], dtype=pl.String),
            "studio": ["Imaginary Pictures"] * len(rows),
            "weekend_gross": [None if v is None else float(v) for v in cols[6]],
            "theater_count": [None if v is None else float(v) for v in cols[7]],
            "total_gross": [None if v is None else float(v) for v in cols[8]],
            "week_num": [float(v) for v in cols[9]],
            "movie_id": pl.Series(cols[4], dtype=pl.String),
            "end_date": pl.Series(cols[2], dtype=pl.Date),
            "release_date": pl.Series(cols[10], dtype=pl.Date),
            "genres": ["Comedy"] * len(rows),
            "mpaa": ["PG"] * len(rows),
        }
    )
    return df.with_columns(**overrides) if overrides else df


# --- fetch and read ---------------------------------------------------------

def test_git_blob_sha1_matches_git():
    assert git_blob_sha1(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    assert git_blob_sha1(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_url_is_pinned_to_a_commit():
    assert stat695.COMMIT in stat695.URL and len(stat695.COMMIT) == 40
    assert stat695.URL.startswith("https://raw.githubusercontent.com/schloerke/stat695data/")


def _cache(content: bytes):
    directory, digest = Fetcher._stem(stat695.URL)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{digest}.rda"
    path.write_bytes(content)
    return path


def test_fetch_offline_cache_miss_raises(repo):
    with pytest.raises(FetchDisabledError):
        stat695.fetch_rda(Fetcher())


def test_fetch_verifies_git_blob(repo, monkeypatch):
    path = _cache(b"not the real file")
    with pytest.raises(stat695.IntegrityError, match="git blob"):
        stat695.fetch_rda(Fetcher())
    monkeypatch.setattr(stat695, "BLOB_SHA1", git_blob_sha1(b"not the real file"))
    assert stat695.fetch_rda(Fetcher()) == path


def write_fixture_rda(path, rows=ROWS):
    """All 21 mojo columns, typed the way create_mojo() left them."""
    cols = list(zip(*rows))
    n = len(rows)
    return write_rda(path, "mojo", {
        "year": Doubles([float(v) for v in cols[0]]),
        "week": Doubles([float(v) for v in cols[1]]),
        "rank_this_week": Doubles([None if v is None else float(v) for v in cols[3]]),
        "rank_last_week": Doubles([None if v is None else float(v) for v in cols[3]]),
        "title": Factor(cols[5]),
        "studio": Factor(["Imaginary Pictures"] * n),
        "weekend_gross": Doubles([None if v is None else float(v) for v in cols[6]]),
        "weekend_gross_perc_change": Doubles([None] * n),
        "theater_count": Doubles([None if v is None else float(v) for v in cols[7]]),
        "theater_change": Doubles([None] * n),
        "average": Doubles([None] * n),
        "total_gross": Doubles([None if v is None else float(v) for v in cols[8]]),
        "budget": Doubles([None] * n),
        "week_num": Doubles([float(v) for v in cols[9]]),
        "movie_id": Factor(cols[4]),
        "start_date": Dates([d - timedelta(days=2) for d in cols[2]]),
        "end_date": Dates(cols[2]),
        "img_loc": Factor([None] * n, levels=["x"]),
        "release_date": Dates(cols[10]),
        "genres": Factor(["Comedy"] * n),
        "mpaa": Factor(["PG"] * n, levels=MPAA_LEVELS, ordered=True),
    })


def test_read_rda_and_normalize(tmp_path):
    raw = stat695.read_rda(write_fixture_rda(tmp_path / "mojo.rda"))
    assert raw.height == 4 and len(raw.columns) == 21
    ing = normalize(raw)
    s = ing.snapshots
    assert s.schema == pl.Schema(stat695.SNAPSHOT_SCHEMA)
    assert s.height == 4
    first = s.row(0, named=True)
    assert first == {
        "weekend_end": date(1983, 1, 9), "release_id": "legacy:moonllama", "title_id": "bb_moonllama",
        "rank": 1, "weekend_gross": 900_000, "theaters": 400, "total_gross": 900_000, "weeks": 1,
        "source": "stat695", "capture_url": None, "is_estimate": False,
    }
    assert s.filter(pl.col("release_id") == "legacy:robotpicnic")["theaters"].null_count() == 2
    rel = ing.releases.row(by_predicate=pl.col("source_key") == "moonllama", named=True)
    assert rel["title"] == "Moon Llama" and rel["distributor"] == "Imaginary Pictures"
    assert rel["release_date"] == date(1983, 1, 7) and rel["mpaa"] == "PG" and rel["genres"] == "Comedy"
    assert (rel["first_weekend"], rel["last_weekend"], rel["weekends"]) == (date(1983, 1, 9), date(1983, 1, 16), 2)
    assert rel["is_rerelease"] is False and rel["label"] is None
    r = ing.report
    assert (r["source_rows"], r["source_releases"], r["snapshot_rows"], r["releases"]) == (4, 2, 4, 2)
    assert r["exact_duplicates_dropped"] == 0 and r["unkeyed_rows"] == 0
    assert (r["weekend_min"], r["weekend_max"], r["weekends"]) == ("1983-01-09", "1983-01-16", 2)
    assert r["nulls"]["theaters"] == 2


def test_read_rda_missing_columns(tmp_path):
    path = write_rda(tmp_path / "bad.rda", "mojo", {"year": Doubles([1983.0])})
    with pytest.raises(ValueError, match="missing columns"):
        stat695.read_rda(path)


def test_read_rda_falls_back_to_the_only_object(tmp_path):
    path = write_fixture_rda(tmp_path / "x.rda")
    data = path.read_bytes()
    assert stat695.read_rda(path).height == 4
    # Same file under another object name still reads.
    import gzip
    raw = gzip.decompress(data).replace(b"\x00\x00\x00\x04mojo", b"\x00\x00\x00\x04MOJO", 1)
    (tmp_path / "y.rda").write_bytes(gzip.compress(raw))
    assert stat695.read_rda(tmp_path / "y.rda").height == 4


# --- normalize: duplicates, unkeyed rows, number handling --------------------

def test_exact_duplicates_dropped_and_reported():
    # A nonexistent week 53 that repeats the next chart word for word.
    repeat = [(1982, 53, *r[2:]) for r in ROWS[:2]]
    ing = normalize(frame(ROWS + repeat))
    assert ing.snapshots.height == 4
    r = ing.report
    assert r["source_rows"] == 6 and r["exact_duplicates_dropped"] == 2
    assert r["duplicate_chart_labels"] == [{"chart": "1982W53", "same_as": "1983W01", "rows": 2}]
    assert r["snapshot_rows"] + r["exact_duplicates_dropped"] + r["unkeyed_rows"] == r["source_rows"]


def test_conflicting_rows_are_kept_not_fixed():
    # Same weekend and release but different figures: not an exact repeat, so both stay.
    clash = [(1982, 53, ROWS[0][2], 1, "moonllama", "Moon Llama", 1, 1, 1, 1, ROWS[0][10])]
    ing = normalize(frame(ROWS + clash))
    assert ing.snapshots.height == 5 and ing.report["exact_duplicates_dropped"] == 0


def test_unkeyed_rows_counted():
    df = frame(ROWS)
    df = df.with_columns(pl.when(pl.int_range(pl.len()) == 3).then(None).otherwise(pl.col("end_date")).alias("end_date"))
    ing = normalize(df)
    assert ing.snapshots.height == 3 and ing.report["unkeyed_rows"] == 1
    assert ing.report["unkeyed_examples"][0]["movie_id"] == "robotpicnic"


def test_fractional_and_nan_values():
    df = frame(ROWS).with_columns(
        pl.Series("weekend_gross", [900_000.4, float("nan"), 700_000.0, 300_000.0])
    )
    ing = normalize(df)
    assert ing.report["nonintegral_values"] == {"weekend_gross": 1}
    assert ing.snapshots["weekend_gross"].to_list() == [900_000, None, 700_000, 300_000]


def test_enum_and_datetime_inputs():
    df = frame(ROWS).with_columns(
        pl.col("title").cast(pl.Enum(sorted({r[5] for r in ROWS}))),
        pl.col("end_date").cast(pl.Datetime("ms")),
    )
    ing = normalize(df)
    assert ing.snapshots["weekend_end"].dtype == pl.Date
    assert set(ing.releases["title"]) == {"Moon Llama", "Robot Picnic"}


def test_string_dates_rejected():
    with pytest.raises(TypeError, match="Date"):
        normalize(frame(ROWS).with_columns(pl.col("end_date").cast(pl.String)))


def test_blank_strings_become_null():
    ing = normalize(frame(ROWS).with_columns(pl.lit("  ").alias("mpaa")))
    assert ing.releases["mpaa"].null_count() == 2


# --- re-release detection ---------------------------------------------------

@pytest.mark.parametrize(
    "title, base, label, kind",
    [
        ("Moon Llama", "Moon Llama", None, None),
        ("Moon Llama (Special Edition)", "Moon Llama", "Special Edition", "reissue"),
        ("Moon Llama (2003 Re-release)", "Moon Llama", "2003 Re-release", "reissue"),
        ("Moon Llama (re-issue)", "Moon Llama", "re-issue", "reissue"),
        ("Moon Llama (Extended Edition)", "Moon Llama", "Extended Edition", "reissue"),
        ("Moon Llama: 20th Anniversary", "Moon Llama", "20th Anniversary", "reissue"),
        ("Moon Llama - The Return - 20th Anniversary", "Moon Llama - The Return", "20th Anniversary", "reissue"),
        ("Moon Llama: The Final Cut", "Moon Llama", "The Final Cut", "weak_reissue"),
        ("Moon Llama - Final Cut", "Moon Llama", "Final Cut", "weak_reissue"),
        ("Moon Llama: The Director's Cut", "Moon Llama", "The Director's Cut", "reissue"),
        ("Moon Llama 3D", "Moon Llama", "3D", "format"),
        ("Moon Llama (3-D)", "Moon Llama", "3-D", "format"),
        ("Moon Llama (IMAX)", "Moon Llama", "IMAX", "format"),
        ("Moon Llama in Disney Digital 3-D", "Moon Llama", "in Disney Digital 3-D", "format"),
        ("Moon Llama: An IMAX 3D Experience", "Moon Llama: An IMAX 3D Experience", None, None),
        ("Moon Llama (An IMAX 3D Experience)", "Moon Llama", "An IMAX 3D Experience", "format"),
        ("Moon Llama 3D (Special Edition)", "Moon Llama", "3D Special Edition", "reissue"),
        ("Moon Llama (2014)", "Moon Llama (2014)", None, None),
        ("Moon Llama: The Sequel", "Moon Llama: The Sequel", None, None),
        ("Robot Picnic Part 3: 3D", "Robot Picnic Part 3", "3D", "format"),
    ],
)
def test_split_title(title, base, label, kind):
    assert split_title(title) == (base, label, kind)


def test_normalize_title():
    assert normalize_title("The Moon Llama & Friends!") == "moon llama and friends"
    assert normalize_title("M.O.O.N.") == "moon"


def rel(movie_id, title, first, dist="Imaginary", release=None):
    return {"movie_id": movie_id, "title": title, "first_weekend": first, "distributor": dist,
            "release_date": release or first}


def detect(*rels):
    return {r["movie_id"]: r for r in detect_rereleases(list(rels))}


def test_title_keyword_links_to_original_from_the_same_distributor():
    out = detect(
        rel("moonllama", "Moon Llama", date(1983, 1, 9)),
        rel("moonllamaspecial", "Moon Llama (Special Edition)", date(1997, 1, 31)),
    )
    r = out["moonllamaspecial"]
    assert (r["is_rerelease"], r["rerelease_reason"], r["parent_movie_id"]) == (True, "title_keyword", "moonllama")
    assert r["label"] == "1997 Special Edition"
    assert out["moonllama"]["is_rerelease"] is False


def test_title_keyword_without_original_in_data():
    r = detect(rel("oldie89", "Oldie (re-issue)", date(1989, 2, 5)))["oldie89"]
    assert r["is_rerelease"] and r["parent_movie_id"] is None and r["label"] == "1989 re-issue"


def test_reissue_is_not_linked_to_a_different_film_with_the_same_title():
    # A 2010 re-issue of an old classic, and an unrelated 1983 film (say, a remake) of the same name.
    out = detect(
        rel("gasp", "Gasp", date(1983, 5, 15), dist="Big Studio"),
        rel("gasp2010reissue", "Gasp (2010 re-issue)", date(2010, 5, 30), dist="Arthouse"),
    )
    r = out["gasp2010reissue"]
    assert r["is_rerelease"] and r["parent_movie_id"] is None


def test_reissues_of_one_classic_link_to_each_other():
    out = detect(
        rel("gasp", "Gasp", date(1983, 5, 15), dist="Big Studio"),
        rel("gasp98", "Gasp (1998 re-issue)", date(1998, 10, 4), dist="Arthouse A"),
        rel("gasp2010", "Gasp (2010 re-issue)", date(2010, 5, 30), dist="Arthouse B"),
    )
    assert out["gasp98"]["parent_movie_id"] is None
    assert out["gasp2010"]["parent_movie_id"] == "gasp98"


def test_weak_reissue_wording_needs_an_earlier_release():
    out = detect(
        rel("moonllama", "Moon Llama", date(1983, 1, 9)),
        rel("moonllamafinal", "Moon Llama: The Final Cut", date(2007, 10, 7)),
        rel("urbanmyth2", "Urban Myth: Final Cut", date(2000, 9, 24)),  # a sequel's title
    )
    assert out["moonllamafinal"]["rerelease_reason"] == "title_keyword"
    assert out["moonllamafinal"]["parent_movie_id"] == "moonllama"
    assert out["urbanmyth2"]["is_rerelease"] is False


def test_format_rerelease_needs_same_distributor_and_a_long_gap():
    out = detect(
        rel("moonllama", "Moon Llama", date(1994, 6, 19)),
        rel("moonllama3d", "Moon Llama 3D", date(2011, 9, 18)),
        rel("dancestep", "Dance Step", date(2006, 8, 13)),
        rel("dancestep3d", "Dance Step 3D", date(2010, 8, 8)),  # a sequel, 4 years on
        rel("nutcase", "The Nutcase", date(1993, 11, 28), dist="Big Studio"),
        rel("nutcase3d", "The Nutcase in 3D", date(2010, 11, 28), dist="Indie"),  # a new film
        rel("oddsaw", "Odd Saw 3D", date(2010, 10, 31)),  # nothing earlier to re-release
    )
    r = out["moonllama3d"]
    assert (r["rerelease_reason"], r["parent_movie_id"], r["label"]) == ("format_rerelease", "moonllama", "2011 3D")
    for mid in ("dancestep3d", "nutcase3d", "oddsaw"):
        assert out[mid]["is_rerelease"] is False and out[mid]["parent_movie_id"] is None, mid


def test_same_title_alone_is_not_a_rerelease():
    out = detect(
        rel("puppet", "Puppet", date(1984, 3, 4)),
        rel("puppet88", "Puppet", date(1988, 6, 5)),
        rel("heat", "Heat", date(1995, 12, 17)),
        rel("theheat", "The Heat", date(2013, 6, 30)),
    )
    assert not any(r["is_rerelease"] for r in out.values())


def test_title_ids_group_rereleases_under_the_root():
    rows = [
        (1983, 1, date(1983, 1, 9), 1, "moonllama", "Moon Llama", 9, 1, 9, 1, date(1983, 1, 7)),
        (1997, 5, date(1997, 2, 2), 1, "moonllamase", "Moon Llama (Special Edition)", 9, 1, 9, 1, date(1997, 1, 31)),
        (2012, 3, date(2012, 1, 22), 1, "moonllama3d", "Moon Llama 3D", 9, 1, 9, 1, date(2012, 1, 20)),
        (1983, 1, date(1983, 1, 9), 2, "robotpicnic", "Robot Picnic", 1, 1, 1, 1, date(1983, 1, 7)),
    ]
    ing = normalize(frame(rows))
    tid = dict(zip(ing.releases["source_key"], ing.releases["title_id"]))
    assert tid == {"moonllama": "bb_moonllama", "moonllamase": "bb_moonllama",
                   "moonllama3d": "bb_moonllama", "robotpicnic": "bb_robotpicnic"}
    parent = dict(zip(ing.releases["source_key"], ing.releases["parent_release_id"]))
    assert parent["moonllama3d"] == "legacy:moonllama"
    assert set(ing.snapshots.filter(pl.col("release_id").str.starts_with("legacy:moonllama"))["title_id"]) == {"bb_moonllama"}
    assert ing.report["rereleases"] == {"title_keyword": 1, "format_rerelease": 1}


def _group(source_key, title_id, label=None):
    return {"source_key": source_key, "title_id": title_id, "release_label": label,
            "source": "x", "source_url": None, "notes": None}


def test_manual_title_groups_win():
    groups = [_group("robotpicnic", "tt0000001", "Director's Cut"), _group("rl123", "tt0000002")]
    ing = normalize(frame(), groups)
    r = ing.releases.row(by_predicate=pl.col("source_key") == "robotpicnic", named=True)
    assert (r["title_id"], r["label"], r["group_source"]) == ("tt0000001", "Director's Cut", "manual")
    assert (r["is_rerelease"], r["rerelease_reason"]) == (True, "manual")
    assert ing.report["manual_groups_applied"] == 1
    assert set(ing.snapshots.filter(pl.col("release_id") == "legacy:robotpicnic")["title_id"]) == {"tt0000001"}


def test_manual_group_without_label_makes_a_standalone_film():
    rows = [
        (1994, 25, date(1994, 6, 19), 1, "moonllama", "Moon Llama", 9, 1, 9, 1, date(1994, 6, 17)),
        (2011, 15, date(2011, 4, 10), 1, "moonllamaimax", "Moon Llama (IMAX)", 9, 1, 9, 1, date(2011, 4, 8)),
    ]
    assert normalize(frame(rows)).releases["title_id"].to_list() == ["bb_moonllama", "bb_moonllama"]
    ing = normalize(frame(rows), [_group("moonllamaimax", "tt0000003")])
    r = ing.releases.row(by_predicate=pl.col("source_key") == "moonllamaimax", named=True)
    assert (r["title_id"], r["is_rerelease"], r["label"], r["parent_release_id"]) == ("tt0000003", False, None, None)


def test_rereleases_follow_a_manually_regrouped_parent():
    rows = [
        (1994, 25, date(1994, 6, 19), 1, "moonllama", "Moon Llama", 9, 1, 9, 1, date(1994, 6, 17)),
        (2011, 37, date(2011, 9, 18), 1, "moonllama3d", "Moon Llama 3D", 9, 1, 9, 1, date(2011, 9, 16)),
    ]
    ing = normalize(frame(rows), [_group("moonllama", "tt0000004")])
    assert ing.releases["title_id"].to_list() == ["tt0000004", "tt0000004"]


def test_provisional_title_ids_are_unique_and_valid():
    ids = provisional_title_ids(["et", "e.t.", "E-T", "", "!!", "moonllama"])
    assert len(set(ids.values())) == 6
    assert ids["et"] == "bb_et" and ids["moonllama"] == "bb_moonllama"
    assert all(TITLE_ID_RE.match(v) for v in ids.values())


# --- outputs ----------------------------------------------------------------

def test_write_outputs(tmp_path):
    rows = ROWS + [(1997, 5, date(1997, 2, 2), 1, "moonllamase", "Moon Llama (Special Edition)",
                    9, 1, 9, 1, date(1997, 1, 31))]
    ing = normalize(frame(rows))
    stat695.write_outputs(ing, tmp_path)
    assert pl.read_parquet(tmp_path / "stat695_snapshots.parquet").equals(ing.snapshots)
    assert pl.read_parquet(tmp_path / "stat695_releases.parquet").height == 3
    import json
    assert json.loads((tmp_path / "stat695_report.json").read_text())["snapshot_rows"] == 5
    review = (tmp_path / "stat695_rereleases.csv").read_text(encoding="utf-8").splitlines()
    assert len(review) == 2 and "legacy:moonllamase" in review[1] and "Moon Llama" in review[1]


def test_run_reads_unmarked_non_utf8_strings(repo, monkeypatch):
    """An unmarked latin-1 title fails as UTF-8; run() retries as Windows-1252 and says so."""
    rows = [(*ROWS[0][:5], "Café Llama".encode("latin-1"), *ROWS[0][6:])]
    directory, digest = Fetcher._stem(stat695.URL)
    directory.mkdir(parents=True)
    path = write_fixture_rda(directory / f"{digest}.rda", rows)
    monkeypatch.setattr(stat695, "BLOB_SHA1", git_blob_sha1(path.read_bytes()))
    with pytest.raises(UnicodeDecodeError):
        stat695.read_rda(path)
    ing = stat695.run()
    assert ing.releases["title"].to_list() == ["Café Llama"]
    assert ing.report["unmarked_string_encoding"] == "WINDOWS-1252"


def test_run_records_utf8(repo, monkeypatch):
    directory, digest = Fetcher._stem(stat695.URL)
    directory.mkdir(parents=True)
    path = write_fixture_rda(directory / f"{digest}.rda")
    monkeypatch.setattr(stat695, "BLOB_SHA1", git_blob_sha1(path.read_bytes()))
    assert stat695.run().report["unmarked_string_encoding"] == "UTF-8"
