"""M2: Box Office Mojo weekend charts, 2017 -> present.

Archives ONLY: captures are located through the Wayback Machine CDX API and
the Common Crawl index, then fetched from web.archive.org / data.commoncrawl.org.
There is no live backend; boxofficemojo.com is hard-blocked in
``boffo_etl.fetch``.
"""

from __future__ import annotations


def load(*args, **kwargs):
    raise NotImplementedError("Box Office Mojo weekend ingest is implemented in M2")
