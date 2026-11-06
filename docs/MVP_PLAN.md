# MVP Plan — Domestic Time Machine (1982 → present)

This is the build plan for Claude Code. Work through the milestones **in order**, and finish each one's acceptance criteria before moving on.
Read `CLAUDE.md`, `docs/DATA_SOURCES.md`, and `docs/DESIGN.md` first.

## MVP definition of done
A static site on GitHub Pages where a visitor can:
1. Search for any film released domestically since 1982, or a major pre-1982 film.
2. Pick any date (weekend granularity) and see the film's **all-time domestic rank** at that date in three measures: **Nominal $**, **CPI-adjusted $**, and **Estimated admissions**.
3. See a chart of that film's all-time rank over time.
4. View the **all-time top 100 as of any date**.
5. View a **director or actor page** with their career total and rank among peers as of any date.
6. View the actual **weekend chart** for any weekend since 1982.

All of it is served as static files, with data queried client-side through DuckDB-WASM.

---

## Architecture

```
etl/                      Python 3.12 package `boffo_etl` (managed with uv)
  sources/
    stat695.py            1982–2016 weekend snapshots (Purdue stat695data mojo.rda)
    bom_weekend.py        2017→present weekend charts (Wayback first, live fallback; cached)
    imdb.py               IMDb non-commercial datasets (titles, crew, principals, names)
    cpi.py                CPI-U monthly (FRED CPIAUCSL / BLS CUUR0000SA0)
  match.py                release → IMDb tconst matching + overrides
  build.py                orchestrates; writes data/build/*.parquet and site/public/data/*.parquet
  checks.py               data-quality checks (also run in CI)
data/
  manual/                 COMMITTED hand-curated CSVs (see below)
  raw/                    gitignored downloads/cache
  build/                  gitignored intermediate outputs
site/                     Vite + React + TypeScript + Tailwind v4 + DuckDB-WASM
  public/data/            COMMITTED final Parquet files (small, a few MB)
tests/                    pytest for ETL; Vitest for site query functions
.github/workflows/        CI (tests + checks) and Pages deploy
```

**Why static and DuckDB-WASM:** total data is small (~150k snapshot rows, ~25k titles, ~100k credits). DuckDB's `ASOF JOIN` computes "latest cumulative total on or before date D" for every film in milliseconds, in the browser. There's no server and no hosting bill.

---

## Data model (Parquet tables shipped to the site)

**`titles.parquet`**: one row per *film* (re-releases grouped)
`title_id` (IMDb tconst, or `bb_xxxx` if unmatched) · `title` · `year` · `release_date` (original domestic) · `distributor` · `genres` · `mpaa` · `pre1982_baseline_gross` (nullable) · `baseline_source`

**`releases.parquet`**: one row per *release* (original, 1985 re-release, special edition…)
`release_id` · `title_id` · `label` (e.g. "1997 Special Edition") · `release_date` · `source_key` (legacy mojo id / BOM rl id)

**`snapshots.parquet`**: one row per release per weekend it charted
`weekend_end` (date, Sunday) · `release_id` · `title_id` · `rank` · `weekend_gross` · `theaters` · `total_gross` (cumulative for that release) · `source` (`stat695` | `wayback` | `bom_live`) · `is_estimate`

**`title_cume.parquet`**: precomputed per title per weekend where it changed (this drives the time machine)
`title_id` · `as_of` (weekend_end) · `cume_nominal` · `cume_cpi` (in constant dollars of a fixed base month; see Inflation) · `cume_admissions`
- `cume_nominal` = baseline + sum over releases of the latest `total_gross` ≤ as_of.
- Built from period deltas: for each release, `delta = total_gross - previous total_gross`. Each delta is deflated by the CPI of its weekend month and divided by the average ticket price of its year. Then take cumulative sums.
- Add one row per title at its first appearance. Pre-1982 baseline titles get a row at `1982-01-01` carrying the baseline.

**`people.parquet`** `person_id` (nconst) · `name` · `primary_profession`
**`credits.parquet`** `title_id` · `person_id` · `role` (`director` | `actor`) · `billing` (int, from IMDb `ordering`)
**`cpi.parquet`** `month` · `cpi`  **`ticket_prices.parquet`** `year` · `avg_price` · `source`

### Committed manual CSVs (`data/manual/`)
- `ticket_prices.csv`: annual US average ticket price, 1910→present, with a `source` column. Seed it from published NATO / Box Office Mojo average-ticket-price tables. Mark gaps as `interpolated`.
- `pre1982_baseline.csv`: the ~150 highest-grossing pre-1982 films, with domestic lifetime gross *as of Dec 31, 1981* (nominal), release year, `is_rental` flag, and a `source` column. This is what keeps all-time lists as of 1984 correct (Star Wars, Jaws, The Exorcist, Gone with the Wind, etc.). Note that later re-release grosses (e.g. Star Wars 1982 re-release) come from snapshots and add on top of the baseline. Don't double count.
- `id_overrides.csv`: `source_key` → `title_id` (and optional `release_label`) for matches the fuzzy matcher gets wrong or can't make.
- `title_groups.csv`: explicit re-release groupings where automatic grouping fails.

---

## Milestones

### M0 — Scaffold (½ day)
- `uv` project for `etl/` (deps: polars or pandas, duckdb, pyreadr, httpx, rapidfuzz, pyarrow, pytest).
- `site/`: Vite + React + TS + Tailwind v4 + `@duckdb/duckdb-wasm` + uPlot (or Observable Plot) + react-router.
- `.gitignore`, `Makefile` or `justfile` with `etl`, `check`, `test`, `site-dev`, `site-build`.
- CI workflow: run pytest and `checks.py` on PRs. Pages deploy workflow on push to `main`.
- **Accept:** `make test` passes (with placeholder tests); the site dev server shows a "Hello 1999" page in the theme from DESIGN.md.

### M1 — Ingest 1982–2016 (stat695data)
- Download `https://github.com/schloerke/stat695data` → `data/mojo.rda` (MIT, Purdue STAT 695). Cache in `data/raw/`.
- Read with `pyreadr`. Columns include: year, week, rank_this_week, title, studio, weekend_gross, theater_count, total_gross, week_num, movie_id (legacy Mojo id like `ongoldenpond`), start_date, end_date, release_date, genres, mpaa. 116,663 rows, 13,499 movie_ids; years 1982–2016 (verify; coverage may extend into early 2017).
- Normalize to the `snapshots` schema (weekend_end = `end_date`). Each legacy `movie_id` becomes one `release`.
- Detect re-releases: legacy ids or titles containing "re-release", "(Special Edition)", "(3D)", "(IMAX)" style suffixes, or a `release_date` far later than an earlier same-title release.
- **Accept:** snapshot count matches the source. No weekend has duplicate ranks. `total_gross` is non-decreasing per release (log and flag violations rather than fixing them silently).

### M2 — Ingest 2017 → present
- Implement `bom_weekend.py` with two backends behind one interface:
  1. **Wayback** (default): use the CDX API to find archived captures of `boxofficemojo.com/weekend/{YYYY}W{WW}/` and fetch the capture *closest after* the weekend's Monday + 7 days (actuals, not Sunday estimates).
  2. **Live** (fallback, opt-in flag `--allow-live`): direct fetch with a 5–10 s delay, a descriptive User-Agent with the repo URL, and on-disk cache. Never re-fetch a cached weekend.
- Parse the weekend table: rank, release name, BOM release id (`rl…`), weekend gross, theaters, total gross, weeks, distributor. Release pages link to IMDb `tt` ids. Collect them, cached, for matching.
- Stitch at the 2016/2017 boundary. Legacy `movie_id` and new `rl` ids are different keys, so carry-over films must be linked through matching (M3).
- **Accept:** every weekend from 1982W01 through the latest completed weekend exists (report gaps). Carry-over films (e.g. late-2016 releases) have continuous `total_gross`.

### M3 — Identity matching (releases → IMDb titles)
- Load IMDb `title.basics` and filter to `titleType in (movie, tvMovie, video)`.
- For new-site releases, use the `tt` id directly.
- For legacy releases, fuzzy match on normalized title (`rapidfuzz`), plus `startYear` within ±1 of the release year, plus runtime and genre agreement as tiebreakers. Strip re-release suffixes before matching.
- Write `data/build/match_report.csv` (score, candidates) and apply `data/manual/id_overrides.csv`.
- **Accept:** ≥ 97% of total nominal gross is matched to a tconst, and 100% of the top 1,000 grossing releases. Unmatched releases keep a `bb_` id and still appear on the site.

### M4 — Credits and people
- From IMDb `title.crew` (directors) and `title.principals` (category actor/actress with `ordering`) plus `name.basics`. Keep only titles in our set.
- Actor rollup rule (configurable; default **top 4 billed**). Directors: all credited directors.
- **Accept:** spot checks pass. Spielberg's titles include Jaws, E.T. and Jurassic Park. Tom Hanks has Toy Story and Forrest Gump.

### M5 — Inflation and admissions
- CPI-U monthly from FRED (`CPIAUCSL`, public domain BLS data) into `cpi.parquet`.
- `ticket_prices.csv` into `ticket_prices.parquet`.
- Build `title_cume` with three measures (see the data model). Store `cume_cpi` in constant base-month dollars. The site rescales to "dollars of the selected date" or "today's dollars" with a toggle.
- Baseline films: CPI and admissions from their release year (approximation; flag `baseline=true`).
- **Accept:** unit tests cover delta deflation on a hand-computed 3-weekend example. Admissions for a known film are within ±5% of a published estimate (document which one).

### M6 — Ranking engine (shared SQL)
- Put the queries in `site/src/queries/*.sql` and run the identical SQL in Python tests against the same Parquet.
  - `leaderboard(as_of, measure, limit, offset, filters)`: ASOF JOIN of titles × latest `title_cume` ≤ as_of, rank with `RANK()`.
  - `film_rank_timeline(title_id, measure)`: the film's rank at every weekend since release. Precompute per title at build time if it's too slow client-side, stored as `rank_timeline/{title_id}.parquet` or one partitioned file.
  - `person_totals(as_of, role, measure)` and `person_rank`.
  - `weekend_chart(weekend_end)`.
- **Golden tests** (verify each against a cited source before locking in, and fix the data if one fails):
  - Domestic nominal #1 all-time switches from Star Wars to E.T. during E.T.'s 1982–83 run.
  - Titanic becomes #1 domestic nominal in spring 1998.
  - Avatar passes Titanic domestic nominal in early 2010.
  - Star Wars: The Force Awakens becomes #1 domestic nominal in January 2016.
  - On the admissions measure, Gone with the Wind stays #1 throughout (requires the baseline).
- **Accept:** golden tests pass. The leaderboard for any date returns in < 300 ms in the browser on a mid-range laptop.

### M7 — Site (per DESIGN.md)
- Pages: Home, Film, Leaderboard, Person, Weekend Chart, About/Data Notes.
- URL state for everything (`/film/tt0120338?date=1998-04-05&m=admissions`) so views are shareable.
- Search: client-side over titles and people (a small prebuilt index JSON, or DuckDB `ILIKE`), keyboard-first.
- Loading: lazy-load DuckDB-WASM and Parquet. Show a 90s-style "Loading… please wait" box with a progress bar.
- Accessibility: WCAG AA contrast, real tables with `<th scope>`, focus styles, `prefers-reduced-motion`.
- **Accept:** Lighthouse scores ≥ 90 for Performance and Accessibility. All six key screens work on mobile and desktop.

### M8 — Data notes and launch
- About page in monospace FAQ style: sources and licenses, what "domestic" means (US + Canada), estimates vs actuals, the baseline approach, CPI vs admissions, re-release grouping, known gaps.
- Footer credits: IMDb non-commercial datasets, Purdue stat695data, Internet Archive, FRED/BLS.
- Deploy to GitHub Pages. Optional: point `boxofficeboffo.com` at it.
- **Accept:** a fresh clone runs `make etl && make site-build` end to end, and the deployed site matches local.

---

## Explicitly out of MVP
Worldwide/international, daily grosses, pre-1982 week-by-week history, studio/franchise/genre rollups, quiz mode, weekly auto-update Action (Phase 2). See `ROADMAP.md`.

## Open decisions (defaults chosen; change anytime)
| Decision | Default |
|---|---|
| Re-releases | Grouped into the title's lifetime total (Mojo convention); release-level view available on the film page |
| Actor credit rule | Top 4 billed |
| Weekend estimates vs actuals | Prefer actuals; store an `is_estimate` flag |
| Date granularity | Weekend (Sunday end date); the date picker snaps to the nearest prior weekend |
| CPI display | "Today's dollars" default, toggle to "dollars of selected date" |
