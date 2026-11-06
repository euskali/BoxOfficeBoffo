# CLAUDE.md — BoxOfficeBoffo

Hobby, non-commercial site: historical domestic box office rankings **as of any date**, with a late-90s fan-site look built with modern Tailwind.

## Read first
- `ROADMAP.md`: phases
- `docs/MVP_PLAN.md`: **the build plan; work milestone by milestone, in order**
- `docs/DATA_SOURCES.md`: sources, terms, fetch etiquette
- `docs/DESIGN.md`: visual direction (web 1.0 aesthetic, modern usability)

## Stack
- ETL: Python 3.12, `uv`, polars/pandas, duckdb, pyreadr, httpx, rapidfuzz, pytest. Package `etl/boffo_etl`.
- Site: Vite + React + TypeScript + Tailwind v4 + DuckDB-WASM + uPlot/Observable Plot. Static, deployed to GitHub Pages.
- Data shipped to the site as Parquet in `site/public/data/` (committed; keep it small).

## Rules
- **Never fetch a URL that's already cached** in `data/raw/`. Live Box Office Mojo fetching is opt-in (`--allow-live`), ≥5 s between requests, project User-Agent. Prefer Wayback / Common Crawl.
- `data/raw/` and `data/build/` are gitignored. `data/manual/*.csv` are hand-curated and committed. Every row needs a `source`.
- Don't silently "fix" data. Flag anomalies (decreasing cumulative totals, duplicate ranks, gaps) in `checks.py` output, and fix via `data/manual/` overrides.
- Rentals ≠ grosses. Keep `is_rental` / `is_estimate` / `baseline` flags all the way to the UI.
- Ranking SQL lives in `site/src/queries/*.sql` and is executed by both the browser and the Python tests. One source of truth.
- Golden tests in M6 must cite where the expected fact comes from.
- Follow `docs/DESIGN.md`: square corners, Verdana, navy header bars, dense zebra tables, underlined blue links, WCAG AA contrast, no blinking or auto-motion.

## Commands (once M0 is done)
- `make etl`: build all Parquet
- `make check`: data-quality report
- `make test`: pytest and vitest
- `make site-dev` / `make site-build`

## Done means
Each milestone's **Accept** criteria in `docs/MVP_PLAN.md` pass. Note progress by ticking the milestone checklist in `README.md`.
