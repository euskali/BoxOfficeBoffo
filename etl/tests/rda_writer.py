"""Minimal writer for R's .rda format (XDR serialization, version 2), for test fixtures.

pyreadr's own writer stores dates as strings and can't write ordered factors, so
fixtures made with it wouldn't look like the real ``mojo.rda``. This writes the
same R types that ``save()`` produces for a tibble: numeric, integer, character,
factor, ordered factor and ``Date`` columns. Only what the tests need.
"""

from __future__ import annotations

import gzip
import math
import struct
from datetime import date
from pathlib import Path
from typing import Sequence

NILVALUE = 254
LISTSXP, SYMSXP, CHARSXP, INTSXP, REALSXP, STRSXP, VECSXP = 2, 1, 9, 13, 14, 16, 19
IS_OBJECT, HAS_ATTR, HAS_TAG = 1 << 8, 1 << 9, 1 << 10
UTF8 = 1 << 3
NA_INT = -(2**31)
NA_REAL = struct.pack(">Q", 0x7FF00000000007A2)
EPOCH = date(1970, 1, 1)


class Factor:
    def __init__(self, values: Sequence[str | bytes | None], levels: Sequence[str | bytes] | None = None,
                 ordered: bool = False) -> None:
        self.values = list(values)
        self.levels = list(levels) if levels is not None else sorted({v for v in values if v is not None})
        self.ordered = ordered


class Dates:
    def __init__(self, values: Sequence[date | None]) -> None:
        self.values = list(values)


class Doubles:
    def __init__(self, values: Sequence[float | None]) -> None:
        self.values = list(values)


class _Out:
    def __init__(self) -> None:
        self.buf = bytearray()

    def int(self, v: int) -> None:
        self.buf += struct.pack(">i", v)

    def flags(self, sexptype: int, *, obj: bool = False, attr: bool = False,
              tag: bool = False, levels: int = 0) -> None:
        self.int(sexptype | (IS_OBJECT if obj else 0) | (HAS_ATTR if attr else 0)
                 | (HAS_TAG if tag else 0) | (levels << 12))

    def charsxp(self, s: str | bytes | None) -> None:
        """A string. ``bytes`` are written as-is with no encoding mark, like a native string."""
        if s is None:
            self.flags(CHARSXP)
            self.int(-1)
            return
        raw = s if isinstance(s, bytes) else s.encode("utf-8")
        self.flags(CHARSXP, levels=0 if isinstance(s, bytes) else UTF8)
        self.int(len(raw))
        self.buf += raw

    def strsxp(self, values: Sequence[str | bytes | None], attrs: list | None = None, obj: bool = False) -> None:
        self.flags(STRSXP, attr=bool(attrs), obj=obj)
        self.int(len(values))
        for v in values:
            self.charsxp(v)
        self.attrs(attrs)

    def realsxp(self, values: Sequence[float | None], attrs: list | None = None, obj: bool = False) -> None:
        self.flags(REALSXP, attr=bool(attrs), obj=obj)
        self.int(len(values))
        for v in values:
            self.buf += NA_REAL if v is None or (isinstance(v, float) and math.isnan(v)) else struct.pack(">d", v)
        self.attrs(attrs)

    def intsxp(self, values: Sequence[int | None], attrs: list | None = None, obj: bool = False) -> None:
        self.flags(INTSXP, attr=bool(attrs), obj=obj)
        self.int(len(values))
        for v in values:
            self.int(NA_INT if v is None else v)
        self.attrs(attrs)

    def attrs(self, attrs: list | None) -> None:
        """Write a tagged pairlist of (name, writer-callable) attributes."""
        if not attrs:
            return
        for name, write_value in attrs:
            self.flags(LISTSXP, tag=True)
            self.flags(SYMSXP)
            self.charsxp(name)
            write_value()
        self.int(NILVALUE)

    def column(self, col) -> None:
        if isinstance(col, Factor):
            codes = {lvl: i + 1 for i, lvl in enumerate(col.levels)}
            cls = ["ordered", "factor"] if col.ordered else ["factor"]
            self.intsxp([None if v is None else codes[v] for v in col.values], obj=True, attrs=[
                ("levels", lambda: self.strsxp(col.levels)),
                ("class", lambda: self.strsxp(cls)),
            ])
        elif isinstance(col, Dates):
            days = [None if d is None else float((d - EPOCH).days) for d in col.values]
            self.realsxp(days, obj=True, attrs=[("class", lambda: self.strsxp(["Date"]))])
        elif isinstance(col, Doubles):
            self.realsxp(col.values)
        elif col and all(v is None or isinstance(v, (str, bytes)) for v in col):
            self.strsxp(col)
        else:
            raise TypeError(f"unsupported fixture column: {col!r}")


def write_rda(path: Path, name: str, columns: dict[str, object]) -> Path:
    """Write ``columns`` as a tibble named ``name`` into a gzip-compressed .rda file."""
    lengths = {len(c.values) if hasattr(c, "values") else len(c) for c in columns.values()}
    if len(lengths) != 1:
        raise ValueError(f"columns have different lengths: {lengths}")
    n = lengths.pop()
    out = _Out()
    out.buf += b"X\n"
    out.int(2)  # serialization format version
    out.int(0x030302)  # written by R 3.3.2, like the 2017 original
    out.int(0x020300)  # readable by R >= 2.3.0
    # The file holds a pairlist: name = data frame.
    out.flags(LISTSXP, tag=True)
    out.flags(SYMSXP)
    out.charsxp(name)
    out.flags(VECSXP, obj=True, attr=True)
    out.int(len(columns))
    for col in columns.values():
        out.column(col)
    out.attrs([
        ("names", lambda: out.strsxp(list(columns))),
        ("row.names", lambda: out.intsxp([None, -n])),  # R's compact form for 1..n
        ("class", lambda: out.strsxp(["tbl_df", "tbl", "data.frame"])),
    ])
    out.int(NILVALUE)
    path.write_bytes(gzip.compress(b"RDX2\n" + bytes(out.buf)))
    return path
