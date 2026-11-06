"""Identity matching (M3): release -> title_id.

Planned behavior:

* Releases that carry a Wikidata P1237 (legacy Box Office Mojo film ID) match
  directly to the Wikidata item, and from there to its P345 IMDb ID.
* Otherwise fall back to fuzzy matching (rapidfuzz) on normalized title, with
  release year within +/-1 of Wikidata/IMDb start year, and runtime/genre
  agreement as tiebreakers. Re-release suffixes are stripped first.
* Write data/build/match_report.csv (score, candidates) and apply
  data/manual/id_overrides.csv last.
* Unmatched releases keep a ``bb_`` title_id.
"""

from __future__ import annotations


def match_releases(*args, **kwargs):
    raise NotImplementedError("release matching is implemented in M3")
