"""M3/M4: film identity and credits from Wikidata (CC0).

Properties used: title labels, P345 (IMDb ID), P1237 (legacy Box Office Mojo
film ID), P57 (director), P161 (cast member) with the P1545 series-ordinal
qualifier as billing order. Queried via the allow-listed Wikidata/QLever
endpoints in ``boffo_etl.fetch``.
"""

from __future__ import annotations


def load(*args, **kwargs):
    raise NotImplementedError("Wikidata ingest is implemented in M3/M4")
