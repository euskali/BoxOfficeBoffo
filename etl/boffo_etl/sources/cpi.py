"""M5: CPI-U monthly, U.S. city average, all items, not seasonally adjusted.

Source: U.S. Bureau of Labor Statistics series CUUR0000SA0 (1913 onward),
public domain; cite BLS. Fetched straight from BLS (the Public Data API at
api.bls.gov, or the flat files at download.bls.gov) through ``boffo_etl.fetch``,
in CI only, and written to ``cpi.parquet``.

FRED is deliberately not used: its terms of use bar scraping and caching FRED
content, and its API needs a registered key.
"""

from __future__ import annotations


def load(*args, **kwargs):
    raise NotImplementedError("CPI ingest is implemented in M5")
