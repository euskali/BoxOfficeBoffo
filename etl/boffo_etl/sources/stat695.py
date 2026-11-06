"""M1: 1982-2016 weekend snapshots from Purdue's stat695data ``mojo.rda``.

Source: the stat695data R package by Barret Schloerke (MIT licensed), pinned to
one commit so the input never changes. The file is fetched through
``boffo_etl.fetch`` (raw.githubusercontent.com, CI only), checked against its
git blob id, and read with pyreadr.

Output, written to ``data/build/``:

* ``stat695_snapshots.parquet``: one row per release per charted weekend
  (``weekend_end`` = the chart's ``end_date``).
* ``stat695_releases.parquet``: one row per legacy Box Office Mojo ``movie_id``,
  with re-release detection and a provisional ``bb_`` title_id. M3 replaces
  title_ids with IMDb tconsts from Wikidata.
* ``stat695_report.json``: row-count reconciliation and source anomalies.
* ``stat695_rereleases.csv``: every detected re-release, for review.

Nothing is fixed silently. Rows that can't be keyed and exact duplicate rows
are counted in the report, and ``checks.py`` flags them.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import polars as pl
from rapidfuzz import fuzz

from .. import paths
from ..fetch import Fetcher, default_fetcher
from ..manual import load_manual

SOURCE = "stat695"
COMMIT = "7a8d5bb7bae42d2186ddea01d2a523671ed348ab"  # schloerke/stat695data master, 2017-04-13
URL = f"https://raw.githubusercontent.com/schloerke/stat695data/{COMMIT}/data/mojo.rda"
BLOB_SHA1 = "3396a9385d30d87a83087fa5f8acc80fef24dac6"  # git blob id of data/mojo.rda at COMMIT
OBJECT_NAME = "mojo"
# From the package docs (man/mojo.Rd at COMMIT). checks.py warns if the file disagrees.
DOCUMENTED_ROWS = 116_663
DOCUMENTED_RELEASES = 13_499

# Columns of the 21 in mojo.rda that the ingest reads.
USED_COLUMNS = (
    "year", "week", "rank_this_week", "title", "studio", "weekend_gross", "theater_count",
    "total_gross", "week_num", "movie_id", "end_date", "release_date", "genres", "mpaa",
)

RELEASE_ID_PREFIX = "legacy:"

# Re-release detection thresholds (see detect_rereleases).
FORMAT_MIN_GAP = timedelta(days=7 * 365)  # 3D/IMAX version of a film first charted 7+ years earlier
SAME_TITLE_MIN_GAP = timedelta(days=2 * 365)  # same title charting again 2+ years later
RELEASE_DATE_GAP = timedelta(days=365)  # first charted a year or more after its release date
ID_SIMILARITY = 85  # rapidfuzz ratio between base titles for a legacy-id suffix match

EXAMPLES = 10  # examples kept per anomaly in the report
FALLBACK_ENCODING = "WINDOWS-1252"  # for unmarked strings that fail to decode as UTF-8


@dataclass
class Ingest:
    snapshots: pl.DataFrame
    releases: pl.DataFrame
    report: dict


class IntegrityError(Exception):
    """The cached file is not the pinned mojo.rda."""


# --- fetch and read ---------------------------------------------------------

def git_blob_sha1(data: bytes) -> str:
    """The id git gives a file's contents (what the GitHub tree API reports)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def fetch_rda(fetcher: Fetcher | None = None) -> Path:
    path = (fetcher or default_fetcher).fetch(URL, suffix=".rda")
    got = git_blob_sha1(path.read_bytes())
    if got != BLOB_SHA1:
        raise IntegrityError(
            f"{path} is not data/mojo.rda at commit {COMMIT[:12]} (git blob {got}, expected "
            f"{BLOB_SHA1}). Delete the cached file, or bump the raw cache prefix in deploy.yml."
        )
    return path


def read_rda(path: Path, encoding: str | None = None) -> pl.DataFrame:
    """Read the mojo data frame. ``encoding`` applies to strings with no encoding mark."""
    import pyreadr

    objects = pyreadr.read_r(str(path), output_format="polars", encoding=encoding)
    if OBJECT_NAME in objects:
        df = objects[OBJECT_NAME]
    elif len(objects) == 1:
        df = next(iter(objects.values()))
    else:
        raise ValueError(f"{path}: expected an object named {OBJECT_NAME!r}, found {list(objects)}")
    missing = [c for c in USED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}; found {df.columns}")
    return df


# --- column conversion ------------------------------------------------------

def _all_null(s: pl.Series) -> bool:
    return s.null_count() == s.len()


def _text(raw: pl.DataFrame, col: str) -> pl.Expr:
    """Factor/character column -> trimmed string, empty -> null."""
    if _all_null(raw[col]):
        return pl.lit(None, pl.String).alias(col)
    s = pl.col(col).cast(pl.String).str.strip_chars()
    return pl.when(s == "").then(None).otherwise(s).alias(col)


def _date(raw: pl.DataFrame, col: str) -> pl.Expr:
    dtype = raw.schema[col]
    if dtype == pl.Date:
        return pl.col(col)
    if isinstance(dtype, pl.Datetime):
        return pl.col(col).dt.date()
    if _all_null(raw[col]):
        return pl.lit(None, pl.Date).alias(col)
    raise TypeError(f"{col} should be an R Date column, got {dtype}")


def _whole(raw: pl.DataFrame, col: str, dtype: pl.DataType, nonintegral: dict[str, int]) -> pl.Expr:
    """R numeric (double) column of whole numbers -> integer. Counts any fractional values."""
    s = raw[col]
    if _all_null(s):
        return pl.lit(None, dtype).alias(col)
    if s.dtype.is_float():
        s = s.fill_nan(None)
        nonintegral[col] = int(((s - s.round(0)).abs() > 1e-6).sum())
        return pl.col(col).fill_nan(None).round(0).cast(dtype)
    if s.dtype.is_integer():
        return pl.col(col).cast(dtype)
    raise TypeError(f"{col} should be numeric, got {s.dtype}")


def _label(year: object, week: object) -> str:
    return f"{year}W{int(week):02d}" if year is not None and week is not None else "unknown"


def _jsonable(rows: list[dict]) -> list[dict]:
    return [{k: (v.isoformat() if isinstance(v, date) else v) for k, v in r.items()} for r in rows]


# --- re-release detection ---------------------------------------------------

REISSUE_RE = re.compile(
    r"\bre-?releas|\bre-?issue|\breissue|anniversary|special edition|director'?s cut|"
    r"remaster|\brestor(?:ed|ation)\b|extended (?:cut|edition)|final cut|collector'?s edition",
    re.I,
)
FORMAT_RE = re.compile(r"(?:in\s+)?(?:an\s+)?(?:imax\s*3-?d|imax|3-?d|digital 3-?d)(?:\s+experience)?", re.I)
PAREN_SUFFIX_RE = re.compile(r"^(?P<base>.*\S)\s*\((?P<suffix>[^()]+)\)\s*$")
BARE_FORMAT_SUFFIX_RE = re.compile(r"^(?P<base>.*\S)\s+(?P<suffix>(?:in\s+)?(?:imax\s*3-?d|imax|3-?d))\s*$", re.I)
SEP_SUFFIX_RE = re.compile(r"^(?P<base>.*\S)\s*(?::|\s-\s|\s\u2013\s)\s*(?P<suffix>[^:]+)$")
ID_REISSUE_SUFFIX_RE = re.compile(r"(?:rerelease|reissue|re|se|specialedition|\d{1,2}th(?:anniversary)?|anniversary)$")
ID_FORMAT_SUFFIX_RE = re.compile(r"(?:imax3d|imax|3d)$")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def split_title(title: str) -> tuple[str, str | None, str | None]:
    """Split a charted title into (base title, suffix label, suffix kind).

    Kind is ``"reissue"`` for re-release wording (re-release, special edition,
    anniversary...), ``"format"`` for 3D/IMAX versions, else None. Other
    parentheticals, such as a remake's "(2014)", stay part of the base title.
    """
    base = title.strip()
    labels: list[str] = []
    kind: str | None = None
    for _ in range(3):
        suffix = None
        m = PAREN_SUFFIX_RE.match(base)
        if m and (REISSUE_RE.search(m["suffix"]) or FORMAT_RE.fullmatch(m["suffix"].strip())):
            suffix = m["suffix"]
        else:
            m = BARE_FORMAT_SUFFIX_RE.match(base)
            if m:
                suffix = m["suffix"]
            else:
                m = SEP_SUFFIX_RE.match(base)
                if m and REISSUE_RE.search(m["suffix"]):
                    suffix = m["suffix"]
        if suffix is None:
            break
        this = "reissue" if REISSUE_RE.search(suffix) else "format"
        kind = "reissue" if "reissue" in (kind, this) else this
        labels.insert(0, suffix.strip())
        base = m["base"].rstrip(" :-\u2013")
    return base, (" ".join(labels) or None), kind


def normalize_title(title: str) -> str:
    t = title.lower().replace("&", " and ")
    t = re.sub(r"['\u2019`.]", "", t)
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    return re.sub(r"^(the|a|an) ", "", t)


def provisional_title_ids(movie_ids: list[str]) -> dict[str, str]:
    """``bb_`` ids from legacy movie_ids, made unique and valid for manual.TITLE_ID_RE."""
    out: dict[str, str] = {}
    taken: set[str] = set()
    for mid in sorted(movie_ids):
        slug = re.sub(r"[^a-z0-9]+", "_", mid.lower()).strip("_")
        tid = f"bb_{slug}" if slug else ""
        if not slug or tid in taken:
            tid = f"bb_{slug + '_' if slug else ''}{hashlib.sha1(mid.encode()).hexdigest()[:6]}"
        taken.add(tid)
        out[mid] = tid
    return out


def _year_of(r: dict) -> int:
    """Year for a re-release label: its release date, unless that is an older original's date."""
    d = r["release_date"]
    if d is not None and d >= r["first_weekend"] - RELEASE_DATE_GAP:
        return d.year
    return r["first_weekend"].year


def _with_year(label: str, year: int) -> str:
    return label if YEAR_RE.search(label) else f"{year} {label}"


def detect_rereleases(rels: list[dict]) -> list[dict]:
    """Mark re-releases and link each to the release it re-releases.

    ``rels`` items need movie_id, title, release_date and first_weekend. Rules,
    first match wins:

    1. ``title_keyword``: the title carries re-release wording, e.g. "(Special Edition)".
    2. ``id_suffix``: the legacy id is an earlier release's id plus a re-release
       suffix (``starwars`` -> ``starwarsse``) and the titles agree.
    3. ``format_rerelease``: a 3D/IMAX title or id suffix, and the same film first
       charted 7+ years earlier. Sequels like "Step Up 3D" come sooner.
    4. ``release_date_gap``: first charted a year or more after its release date,
       e.g. Star Wars (1977) charting in 1982.
    5. ``same_title_later``: same title as a release first charted 2+ years
       earlier. Remakes can trip this; M3's Wikidata matching has the final say.

    Adds base_title, label, is_rerelease, rerelease_reason and parent_movie_id.
    """
    rels = sorted(rels, key=lambda r: (r["first_weekend"], r["movie_id"]))
    by_id = {r["movie_id"]: r for r in rels}
    earliest_by_base: dict[str, dict] = {}
    for r in rels:
        base, suffix, kind = split_title(r["title"] or r["movie_id"])
        r.update(base_title=normalize_title(base) or r["movie_id"], suffix=suffix, suffix_kind=kind,
                 label=None, is_rerelease=False, rerelease_reason=None, parent_movie_id=None)

    def id_parent(r: dict, pattern: re.Pattern[str]) -> dict | None:
        m = pattern.search(r["movie_id"])
        if not m or m.start() == 0:
            return None
        p = by_id.get(r["movie_id"][: m.start()])
        if p is None or p["first_weekend"] >= r["first_weekend"]:
            return None
        return p if fuzz.ratio(p["base_title"], r["base_title"]) >= ID_SIMILARITY else None

    for r in rels:
        same = earliest_by_base.get(r["base_title"])
        year = _year_of(r)
        if r["suffix_kind"] == "reissue":
            parent = id_parent(r, ID_REISSUE_SUFFIX_RE) or id_parent(r, ID_FORMAT_SUFFIX_RE) or same
            r.update(is_rerelease=True, rerelease_reason="title_keyword", label=_with_year(r["suffix"], year))
        elif p := id_parent(r, ID_REISSUE_SUFFIX_RE):
            parent = p
            r.update(is_rerelease=True, rerelease_reason="id_suffix",
                     label=_with_year(r["suffix"], year) if r["suffix"] else f"{year} re-release")
        elif (r["suffix_kind"] == "format" or ID_FORMAT_SUFFIX_RE.search(r["movie_id"])) and (
            p := id_parent(r, ID_FORMAT_SUFFIX_RE) or same
        ) and r["first_weekend"] - p["first_weekend"] >= FORMAT_MIN_GAP:
            parent = p
            r.update(is_rerelease=True, rerelease_reason="format_rerelease",
                     label=_with_year(r["suffix"] or "re-release", year))
        elif r["release_date"] is not None and r["first_weekend"] - r["release_date"] >= RELEASE_DATE_GAP:
            parent = same
            r.update(is_rerelease=True, rerelease_reason="release_date_gap",
                     label=f"{r['first_weekend'].year} re-release")
        elif same is not None and not r["suffix_kind"] and r["first_weekend"] - same["first_weekend"] >= SAME_TITLE_MIN_GAP:
            parent = same
            r.update(is_rerelease=True, rerelease_reason="same_title_later", label=f"{year} re-release")
        else:
            parent = None
        if parent is not None:
            r["parent_movie_id"] = parent["movie_id"]
        earliest_by_base.setdefault(r["base_title"], r)
    return rels


def _root(movie_id: str, parent_of: dict[str, str | None]) -> str:
    seen = {movie_id}
    while (p := parent_of.get(movie_id)) is not None and p not in seen:
        seen.add(p)
        movie_id = p
    return movie_id


# --- normalize --------------------------------------------------------------

SNAPSHOT_SCHEMA = {
    "weekend_end": pl.Date, "release_id": pl.String, "title_id": pl.String, "rank": pl.Int32,
    "weekend_gross": pl.Int64, "theaters": pl.Int32, "total_gross": pl.Int64, "weeks": pl.Int32,
    "source": pl.String, "capture_url": pl.String, "is_estimate": pl.Boolean,
}
RELEASE_SCHEMA = {
    "release_id": pl.String, "title_id": pl.String, "label": pl.String, "release_date": pl.Date,
    "source_key": pl.String, "source": pl.String, "title": pl.String, "distributor": pl.String,
    "genres": pl.String, "mpaa": pl.String, "first_weekend": pl.Date, "last_weekend": pl.Date,
    "weekends": pl.Int32, "is_rerelease": pl.Boolean, "rerelease_reason": pl.String,
    "parent_release_id": pl.String, "group_source": pl.String,
}


def normalize(raw: pl.DataFrame, title_groups: list[dict] | None = None) -> Ingest:
    """Turn the raw mojo data frame into snapshots and releases."""
    nonintegral: dict[str, int] = {}
    df = raw.with_row_index("_row").select(
        "_row",
        _whole(raw, "year", pl.Int32, nonintegral).alias("chart_year"),
        _whole(raw, "week", pl.Int32, nonintegral).alias("chart_week"),
        _date(raw, "end_date").alias("weekend_end"),
        _text(raw, "movie_id"),
        _whole(raw, "rank_this_week", pl.Int32, nonintegral).alias("rank"),
        _whole(raw, "weekend_gross", pl.Int64, nonintegral).alias("weekend_gross"),
        _whole(raw, "theater_count", pl.Int32, nonintegral).alias("theaters"),
        _whole(raw, "total_gross", pl.Int64, nonintegral).alias("total_gross"),
        _whole(raw, "week_num", pl.Int32, nonintegral).alias("weeks"),
        _text(raw, "title"),
        _text(raw, "studio"),
        _date(raw, "release_date").alias("release_date"),
        _text(raw, "genres"),
        _text(raw, "mpaa"),
    )

    # Rows without a weekend or a movie id can't become snapshots.
    keyed = pl.col("weekend_end").is_not_null() & pl.col("movie_id").is_not_null()
    unkeyed = df.filter(~keyed)
    df = df.filter(keyed)

    # Exact repeats of a row under another chart label (same weekend, release and figures).
    dup_key = ["weekend_end", "movie_id", "rank", "weekend_gross", "theaters", "total_gross", "weeks"]
    df = df.sort("_row").with_columns(pl.struct(dup_key).is_first_distinct().alias("_first"))
    dropped = df.filter(~pl.col("_first"))
    kept_label = df.filter(pl.col("_first")).select(
        *dup_key, pl.col("chart_year").alias("kept_year"), pl.col("chart_week").alias("kept_week")
    )
    dup_labels = (
        dropped.join(kept_label, on=dup_key, how="left", nulls_equal=True)
        .group_by("chart_year", "chart_week", "kept_year", "kept_week")
        .agg(pl.len().alias("rows"))
        .sort("chart_year", "chart_week")
    )
    df = df.filter(pl.col("_first")).drop("_first")

    # One release per legacy movie_id; descriptive fields from its earliest charted weekend.
    agg = (
        df.sort("weekend_end", "_row")
        .group_by("movie_id", maintain_order=True)
        .agg(
            pl.col("title").drop_nulls().first(),
            pl.col("studio").drop_nulls().first().alias("distributor"),
            pl.col("release_date").drop_nulls().first(),
            pl.col("genres").drop_nulls().first(),
            pl.col("mpaa").drop_nulls().first(),
            pl.col("weekend_end").min().alias("first_weekend"),
            pl.col("weekend_end").max().alias("last_weekend"),
            pl.len().cast(pl.Int32).alias("weekends"),
            pl.col("title").drop_nulls().n_unique().alias("_n_title"),
            pl.col("studio").drop_nulls().n_unique().alias("_n_studio"),
            pl.col("release_date").drop_nulls().n_unique().alias("_n_release_date"),
        )
    )
    varying = {
        name: agg.filter(pl.col(f"_n_{name}") > 1).height
        for name in ("title", "studio", "release_date")
    }

    rels = detect_rereleases(agg.drop("_n_title", "_n_studio", "_n_release_date").to_dicts())
    parent_of = {r["movie_id"]: r["parent_movie_id"] for r in rels}
    tids = provisional_title_ids([r["movie_id"] for r in rels])
    for r in rels:
        r["title_id"] = tids[_root(r["movie_id"], parent_of)]
        r["group_source"] = "auto"

    # Hand-curated groupings (data/manual/title_groups.csv) win over detection.
    manual_applied = 0
    groups = {g["source_key"]: g for g in (title_groups or [])}
    for r in rels:
        g = groups.get(r["movie_id"])
        if g:
            r["title_id"] = g["title_id"]
            if g.get("release_label"):
                r["label"] = g["release_label"]
            r["group_source"] = "manual"
            manual_applied += 1

    releases = pl.DataFrame(
        [
            {
                "release_id": RELEASE_ID_PREFIX + r["movie_id"],
                "title_id": r["title_id"],
                "label": r["label"],
                "release_date": r["release_date"],
                "source_key": r["movie_id"],
                "source": SOURCE,
                "title": r["title"],
                "distributor": r["distributor"],
                "genres": r["genres"],
                "mpaa": r["mpaa"],
                "first_weekend": r["first_weekend"],
                "last_weekend": r["last_weekend"],
                "weekends": r["weekends"],
                "is_rerelease": r["is_rerelease"],
                "rerelease_reason": r["rerelease_reason"],
                "parent_release_id": RELEASE_ID_PREFIX + r["parent_movie_id"] if r["parent_movie_id"] else None,
                "group_source": r["group_source"],
            }
            for r in rels
        ],
        schema=RELEASE_SCHEMA,
    ).sort("first_weekend", "release_id")

    snapshots = (
        df.join(releases.select("source_key", "title_id"), left_on="movie_id", right_on="source_key", how="left")
        .select(
            "weekend_end",
            (pl.lit(RELEASE_ID_PREFIX) + pl.col("movie_id")).alias("release_id"),
            "title_id", "rank", "weekend_gross", "theaters", "total_gross", "weeks",
            pl.lit(SOURCE).alias("source"),
            pl.lit(None, pl.String).alias("capture_url"),
            # Scraped in March 2017, after every 1982-2016 weekend had reported actuals.
            pl.lit(False).alias("is_estimate"),
        )
        .cast(SNAPSHOT_SCHEMA)
        .sort("weekend_end", "rank", "release_id", nulls_last=True)
    )

    reasons = releases.filter(pl.col("is_rerelease"))["rerelease_reason"].value_counts(sort=True)
    report = {
        "source": SOURCE,
        "url": URL,
        "commit": COMMIT,
        "blob_sha1": BLOB_SHA1,
        "documented_rows": DOCUMENTED_ROWS,
        "documented_releases": DOCUMENTED_RELEASES,
        "source_rows": raw.height,
        "source_releases": raw.select(_text(raw, "movie_id")).drop_nulls().n_unique(),
        "unkeyed_rows": unkeyed.height,
        "unkeyed_examples": _jsonable(
            unkeyed.select("_row", "chart_year", "chart_week", "weekend_end", "movie_id", "title")
            .head(EXAMPLES).to_dicts()
        ),
        "exact_duplicates_dropped": dropped.height,
        "duplicate_chart_labels": [
            {"chart": _label(d["chart_year"], d["chart_week"]),
             "same_as": _label(d["kept_year"], d["kept_week"]), "rows": d["rows"]}
            for d in dup_labels.to_dicts()
        ],
        "snapshot_rows": snapshots.height,
        "releases": releases.height,
        "weekends": snapshots["weekend_end"].n_unique(),
        "weekend_min": str(snapshots["weekend_end"].min()) if snapshots.height else None,
        "weekend_max": str(snapshots["weekend_end"].max()) if snapshots.height else None,
        "nonintegral_values": {k: v for k, v in nonintegral.items() if v},
        "nulls": {c: snapshots[c].null_count() for c in ("rank", "weekend_gross", "theaters", "total_gross", "weeks")},
        "releases_missing_release_date": releases["release_date"].null_count(),
        "releases_with_varying": varying,
        "rereleases": {d["rerelease_reason"]: d["count"] for d in reasons.to_dicts()},
        "manual_groups_applied": manual_applied,
    }
    return Ingest(snapshots=snapshots, releases=releases, report=report)


# --- build step -------------------------------------------------------------

def write_outputs(ingest: Ingest, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    ingest.snapshots.write_parquet(out_dir / "stat695_snapshots.parquet")
    ingest.releases.write_parquet(out_dir / "stat695_releases.parquet")
    (out_dir / "stat695_report.json").write_text(json.dumps(ingest.report, indent=2) + "\n", encoding="utf-8")
    rel = ingest.releases
    parents = rel.select(pl.col("release_id").alias("parent_release_id"), pl.col("title").alias("parent_title"),
                         pl.col("first_weekend").alias("parent_first_weekend"))
    review = (
        rel.filter(pl.col("is_rerelease") | (pl.col("group_source") == "manual"))
        .join(parents, on="parent_release_id", how="left")
        .select("release_id", "title", "first_weekend", "release_date", "label", "rerelease_reason",
                "group_source", "parent_release_id", "parent_title", "parent_first_weekend", "title_id")
        .sort("rerelease_reason", "first_weekend", "release_id")
    )
    with (out_dir / "stat695_rereleases.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(review.columns)
        for row in review.iter_rows():
            w.writerow(["" if v is None else v for v in row])


def run(fetcher: Fetcher | None = None) -> Ingest:
    """Build step: fetch (CI only), read, normalize, write to data/build/."""
    path = fetch_rda(fetcher)
    encoding = "UTF-8"
    try:
        raw = read_rda(path)
    except UnicodeDecodeError:
        # Unmarked strings that aren't UTF-8; checks.py flags the fallback.
        encoding = FALLBACK_ENCODING
        raw = read_rda(path, encoding=encoding)
    ingest = normalize(raw, load_manual("title_groups.csv"))
    ingest.report["unmarked_string_encoding"] = encoding
    write_outputs(ingest, paths.data_build())
    r = ingest.report
    print(
        f"  stat695: {r['source_rows']} source rows -> {r['snapshot_rows']} snapshots "
        f"({r['exact_duplicates_dropped']} exact duplicates, {r['unkeyed_rows']} unkeyed), "
        f"{r['releases']} releases, weekends {r['weekend_min']} to {r['weekend_max']}"
    )
    return ingest
