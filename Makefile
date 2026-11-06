# BoxOfficeBozo task runner. CI runs these same targets.
# Windows: install GNU make (e.g. `winget install ezwinports.make`) or run the commands by hand.

UV  ?= uv
NPM ?= npm
ETL  = $(UV) --directory etl run

.DEFAULT_GOAL := help
.PHONY: help setup etl check test test-py test-site site-dev site-build guard clean

help:
	@echo "make setup       install Python (uv) and Node (npm ci) dependencies from the lockfiles"
	@echo "make etl         build Parquet into site/public/data (offline unless BOFFO_FETCH=1; CI sets it)"
	@echo "make check       data-quality report: manual CSV sources + built tables"
	@echo "make test        pytest + vitest"
	@echo "make site-dev    Vite dev server"
	@echo "make site-build  production build into site/dist"
	@echo "make guard       fail if built or scraped data is tracked by git"

setup:
	$(UV) --directory etl sync --locked
	cd site && $(NPM) ci

etl:
	$(ETL) python -m boffo_etl.build

check:
	$(ETL) python -m boffo_etl.checks

test: test-py test-site

test-py:
	$(ETL) pytest

test-site:
	cd site && $(NPM) test

site-dev:
	cd site && $(NPM) run dev

site-build:
	cd site && $(NPM) run build

guard:
	sh scripts/check-no-data.sh

clean:
	rm -rf data/build site/public/data site/dist
