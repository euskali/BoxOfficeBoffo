#!/bin/sh
# Fails if built, scraped, or derived data is tracked by git.
# Data is built in CI and shipped only in the GitHub Pages artifact (see DATA_NOTICE.md).
set -eu

tracked=$(git ls-files -- \
  'data/raw/*' 'data/build/*' 'site/public/data/*' \
  '*.parquet' '*.rda' '*.rds' '*.RData' '*.duckdb' '*.arrow' '*.feather' \
  '*.warc' '*.warc.gz' '*.wat' '*.wet')

# data/manual/ holds only hand-curated, cited CSVs (plus an optional README).
manual_other=$(git ls-files -- 'data/manual/*' | grep -vE '\.(csv|md)$' || true)

if [ -n "$tracked$manual_other" ]; then
  echo "ERROR: built, scraped, or derived data is tracked by git:" >&2
  printf '%s\n' $tracked $manual_other >&2
  echo "Remove it with 'git rm --cached <file>'. Data is built in CI and shipped only in the Pages artifact." >&2
  exit 1
fi
echo "guard: no built or scraped data tracked by git"
