"""M1: 1982-2016 weekend snapshots from Purdue's stat695data ``mojo.rda``.

Source: the stat695data GitHub repository (MIT licensed), fetched through
``boffo_etl.fetch`` (github.com / raw.githubusercontent.com, CI only) and read
with pyreadr. Normalizes to the ``snapshots`` schema; each legacy ``movie_id``
becomes one release.
"""

from __future__ import annotations


def load(*args, **kwargs):
    raise NotImplementedError("stat695 ingest is implemented in M1")
