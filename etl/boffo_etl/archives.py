"""Web archive lookups: the Wayback Machine CDX API and the Common Crawl index.

Only URL building, response parsing and capture ordering live here; all
network access goes through :class:`boffo_etl.fetch.Fetcher`, so the cache,
the host allowlist and the 5-second spacing apply. Parsers raise ValueError
on a body that isn't a real index answer (an outage page, say), and the
``validate_*`` helpers pass that to ``Fetcher.fetch(validate=...)`` so such a
body is never cached.
"""

from __future__ import annotations

import gzip
import json
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

WAYBACK = "https://web.archive.org"
WAYBACK_CDX = f"{WAYBACK}/cdx/search/cdx"
WAYBACK_FIELDS = ("timestamp", "original", "statuscode", "mimetype", "length")
CC_INDEX = "https://index.commoncrawl.org"
CC_DATA = "https://data.commoncrawl.org"


@dataclass(frozen=True)
class Capture:
    archive: str  # "wayback" | "commoncrawl"
    timestamp: datetime  # UTC
    original: str  # the archived URL as crawled
    status: int | None
    mime: str
    filename: str | None = None  # Common Crawl WARC file, offset and length
    offset: int | None = None
    length: int | None = None
    crawl: str | None = None

    @property
    def ts14(self) -> str:
        return self.timestamp.strftime("%Y%m%d%H%M%S")

    @property
    def is_html(self) -> bool:
        return "html" in (self.mime or "").lower() or self.mime in ("", "unk", "warc/revisit")


def parse_ts(ts: str) -> datetime:
    ts = (ts + "00000000000000")[:14]
    return datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# --- Wayback Machine ----------------------------------------------------------

def wayback_cdx_url(target: str, *, start: str | None = None, to: str | None = None) -> str:
    """Exact-URL CDX query for 200 captures, optionally between ``start`` and ``to`` (CDX timestamps)."""
    params = {"url": target, "output": "json", "fl": ",".join(WAYBACK_FIELDS), "filter": "statuscode:200"}
    if start:
        params["from"] = start
    if to:
        params["to"] = to
    return f"{WAYBACK_CDX}?{urlencode(params)}"


def parse_wayback_cdx(body: bytes) -> list[Capture]:
    text = body.decode("utf-8").strip()
    if not text:
        return []
    rows = json.loads(text)
    if not isinstance(rows, list) or (rows and not isinstance(rows[0], list)):
        raise ValueError("not a CDX JSON answer")
    if not rows:
        return []
    col = {name: i for i, name in enumerate(rows[0])}
    if "timestamp" not in col or "original" not in col:
        raise ValueError(f"CDX answer lacks timestamp/original columns: {rows[0]}")
    out = []
    for r in rows[1:]:
        out.append(Capture(
            archive="wayback",
            timestamp=parse_ts(r[col["timestamp"]]),
            original=r[col["original"]],
            status=_int(r[col["statuscode"]]) if "statuscode" in col else None,
            mime=r[col["mimetype"]] if "mimetype" in col else "",
        ))
    return out


def validate_wayback_cdx(body: bytes) -> None:
    parse_wayback_cdx(body)


def wayback_raw_url(c: Capture) -> str:
    """The capture's original bytes, without the Wayback toolbar or link rewriting."""
    return f"{WAYBACK}/web/{c.ts14}id_/{c.original}"


def wayback_view_url(c: Capture) -> str:
    """The capture as a person would open it in the Wayback Machine."""
    return f"{WAYBACK}/web/{c.ts14}/{c.original}"


def order_candidates(captures: list[Capture], *, earliest: datetime, preferred_after: datetime) -> list[Capture]:
    """Captures to try, best first.

    Only HTML captures at or after ``earliest`` count. First the ones at or
    after ``preferred_after``, oldest first (the closest after it), then the
    earlier ones, newest first.
    """
    seen: set[tuple[str, str]] = set()
    eligible = []
    for c in captures:
        if c.timestamp < earliest or (c.status not in (None, 200)) or not c.is_html:
            continue
        if (c.ts14, c.original) in seen:
            continue
        seen.add((c.ts14, c.original))
        eligible.append(c)
    after = sorted((c for c in eligible if c.timestamp >= preferred_after), key=lambda c: (c.timestamp, c.original))
    before = sorted((c for c in eligible if c.timestamp < preferred_after),
                    key=lambda c: (c.timestamp, c.original), reverse=True)
    return after + before


# --- Common Crawl -------------------------------------------------------------

@dataclass(frozen=True)
class Crawl:
    id: str
    start: datetime
    end: datetime
    cdx_api: str


def cc_collinfo_url(epoch: str) -> str:
    """The crawl list. ``epoch`` (e.g. a year-month) only varies the cache key, so new crawls show up."""
    return f"{CC_INDEX}/collinfo.json?{urlencode({'refresh': epoch})}"


def _iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)


def parse_collinfo(body: bytes) -> list[Crawl]:
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("collinfo.json is not a list")
    out = []
    for c in data:
        if not isinstance(c, dict) or "id" not in c or "cdx-api" not in c:
            raise ValueError(f"unexpected crawl entry: {c!r}")
        try:
            out.append(Crawl(c["id"], _iso(c["from"]), _iso(c["to"]), c["cdx-api"]))
        except (KeyError, ValueError):
            continue  # very old crawls lack usable dates; none of them cover 2017+
    return sorted(out, key=lambda c: c.start)


def validate_collinfo(body: bytes) -> None:
    parse_collinfo(body)


def cc_index_url(crawl: Crawl, target: str) -> str:
    return f"{crawl.cdx_api}?url={quote(target, safe='')}&output=json"


def parse_cc_index(body: bytes) -> list[Capture]:
    """Parse a Common Crawl index answer (JSON lines, or a "No Captures found" message)."""
    text = body.decode("utf-8").strip()
    if not text:
        return []
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if not isinstance(rec, dict):
            raise ValueError("not a Common Crawl index record")
        if "url" not in rec:
            if "message" in rec or "error" in rec:  # "No Captures found for: ..."
                continue
            raise ValueError(f"unexpected index record: {rec!r}")
        out.append(Capture(
            archive="commoncrawl",
            timestamp=parse_ts(rec["timestamp"]),
            original=rec["url"],
            status=_int(rec.get("status")),
            mime=rec.get("mime-detected") or rec.get("mime") or "",
            filename=rec.get("filename"),
            offset=_int(rec.get("offset")),
            length=_int(rec.get("length")),
        ))
    return out


def validate_cc_index(body: bytes) -> None:
    parse_cc_index(body)


def cc_record_url(c: Capture) -> str:
    return f"{CC_DATA}/{c.filename}"


def cc_view_url(c: Capture) -> str:
    """Where the record lives: the WARC file plus its byte range."""
    return f"{CC_DATA}/{c.filename}#offset={c.offset}&length={c.length}"


def _dechunk(data: bytes) -> bytes:
    out = bytearray()
    pos = 0
    while True:
        end = data.find(b"\r\n", pos)
        if end < 0:
            raise ValueError("truncated chunked body")
        size = int(data[pos:end].split(b";")[0].strip() or b"0", 16)
        if size == 0:
            return bytes(out)
        start = end + 2
        out += data[start:start + size]
        pos = start + size + 2


def parse_warc_record(data: bytes) -> tuple[int, dict[str, str], bytes]:
    """One gzipped WARC response record -> (HTTP status, HTTP headers, decoded body)."""
    raw = gzip.decompress(data)
    head, sep, rest = raw.partition(b"\r\n\r\n")
    if not sep or not head.startswith(b"WARC/"):
        raise ValueError("not a WARC record")
    warc = {}
    for line in head.split(b"\r\n")[1:]:
        k, _, v = line.decode("latin-1").partition(":")
        warc[k.strip().lower()] = v.strip()
    if warc.get("warc-type") != "response":
        raise ValueError(f"WARC record is a {warc.get('warc-type')!r}, not a response")
    length = _int(warc.get("content-length"))
    payload = rest[:length] if length is not None else rest
    http_head, sep, body = payload.partition(b"\r\n\r\n")
    if not sep:
        raise ValueError("WARC response has no HTTP header block")
    lines = http_head.decode("latin-1").split("\r\n")
    parts = lines[0].split()
    if len(parts) < 2 or not parts[0].startswith("HTTP/"):
        raise ValueError(f"bad HTTP status line {lines[0]!r}")
    status = int(parts[1])
    headers: dict[str, str] = {}
    for line in lines[1:]:
        k, _, v = line.partition(":")
        headers[k.strip().lower()] = v.strip()
    if "chunked" in headers.get("transfer-encoding", "").lower():
        body = _dechunk(body)
    encoding = headers.get("content-encoding", "").lower()
    if encoding in ("gzip", "x-gzip"):
        body = gzip.decompress(body)
    elif encoding == "deflate":
        body = zlib.decompress(body)
    elif encoding not in ("", "identity"):
        raise ValueError(f"unsupported Content-Encoding {encoding!r}")
    return status, headers, body


def decode_html(body: bytes) -> str:
    """Box Office Mojo pages are UTF-8 since the 2019 redesign; older ones may be Windows-1252."""
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("windows-1252", errors="replace")
