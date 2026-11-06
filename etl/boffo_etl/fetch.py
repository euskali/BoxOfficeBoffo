"""Cached, polite, host-gated HTTP fetcher.

Rules (see docs/DATA_SOURCES.md):

* Offline by default. The network is touched only when ``BOFFO_FETCH=1``
  (set by the CI data-build job). A cache miss otherwise raises
  :class:`FetchDisabledError`.
* Live Box Office Mojo / IMDb / The Numbers fetching is never allowed. Use
  the Wayback Machine or Common Crawl instead.
* Only allow-listed hosts may be contacted; every redirect hop is re-checked.
* A cached URL is never re-fetched.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlsplit

import httpx

from . import paths

USER_AGENT = (
    "BoxOfficeBozo-ETL/0.1 (+https://github.com/euskali/BoxOfficeBozo; "
    "non-commercial hobby project)"
)

# Hosts (and all their subdomains) that must never be fetched live.
DENYLIST: tuple[str, ...] = (
    "boxofficemojo.com",
    "imdb.com",
    "imdbws.com",
    "media-imdb.com",
    "the-numbers.com",
)

# Exact hosts that may be fetched.
ALLOWLIST: tuple[str, ...] = (
    "web.archive.org",
    "archive.org",
    "index.commoncrawl.org",
    "data.commoncrawl.org",
    "query.wikidata.org",
    "www.wikidata.org",
    "qlever.cs.uni-freiburg.de",
    "qlever.dev",
    "download.bls.gov",
    "api.bls.gov",
    "github.com",
    "raw.githubusercontent.com",
    "codeload.github.com",
    "objects.githubusercontent.com",
)

DEFAULT_MIN_INTERVAL = 5.0
MAX_REDIRECTS = 5
MAX_ATTEMPTS = 4
BACKOFF_BASE = 2.0
ENV_FLAG = "BOFFO_FETCH"


class FetchError(Exception):
    """Base class for fetch failures."""


class FetchDisabledError(FetchError):
    """Not cached and network fetching is disabled."""


class BlockedHostError(FetchError):
    """Host is on the permanent denylist."""


class HostNotAllowedError(FetchError):
    """Host is not on the allowlist."""


def _hostname(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().rstrip(".")


def check_url_policy(url: str) -> str:
    """Validate scheme and host. Returns the host. Raises on violation."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchError(f"{url} has unsupported scheme {parts.scheme!r}; only http/https allowed")
    host = _hostname(url)
    if not host:
        raise FetchError(f"{url} has no host")
    for bad in DENYLIST:
        if host == bad or host.endswith("." + bad):
            raise BlockedHostError(
                f"live fetching from {host} is not allowed; use the Wayback Machine "
                "or Common Crawl (see docs/DATA_SOURCES.md)"
            )
    if host not in ALLOWLIST:
        raise HostNotAllowedError(
            f"host {host} is not on the fetch allowlist (boffo_etl.fetch.ALLOWLIST)"
        )
    return host


def _guess_ext(content_type: str | None) -> str:
    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        known = {
            "application/json": ".json",
            "application/sparql-results+json": ".json",
            "text/csv": ".csv",
            "text/html": ".html",
            "application/gzip": ".gz",
            "application/x-gzip": ".gz",
            "text/plain": ".txt",
        }
        if ct in known:
            return known[ct]
        guessed = mimetypes.guess_extension(ct)
        if guessed:
            return guessed
    return ".bin"


class Fetcher:
    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        min_interval: float = DEFAULT_MIN_INTERVAL,
        host_intervals: dict[str, float] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self.min_interval = min_interval
        self.host_intervals = dict(host_intervals or {})
        self._clock = clock
        self._sleep = sleep
        self._last_request: dict[str, float] = {}

    # -- cache -----------------------------------------------------------
    @staticmethod
    def _stem(url: str) -> tuple[Path, str]:
        host = _hostname(url) or "unknown"
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
        return paths.data_raw() / "http" / host, digest

    def _find_cached(self, url: str) -> Path | None:
        directory, digest = self._stem(url)
        if not directory.is_dir():
            return None
        for p in sorted(directory.glob(digest + "*")):
            if p.name.endswith(".meta.json") or p.name.endswith(".tmp"):
                continue
            if p.name == digest or p.name.startswith(digest + "."):
                return p
        return None

    # -- politeness ------------------------------------------------------
    def _wait_turn(self, host: str) -> None:
        interval = self.host_intervals.get(host, self.min_interval)
        last = self._last_request.get(host)
        if last is not None:
            remaining = interval - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[host] = self._clock()

    # -- network ---------------------------------------------------------
    def _get_client(self) -> tuple[httpx.Client, bool]:
        if self._client is not None:
            return self._client, False
        return httpx.Client(timeout=60.0, headers={"User-Agent": USER_AGENT}), True

    def _request_once(self, client: httpx.Client, url: str) -> httpx.Response:
        host = check_url_policy(url)
        self._wait_turn(host)
        return client.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=False)

    def _request_with_retries(self, client: httpx.Client, url: str) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = self._request_once(client, url)
            except httpx.TransportError as exc:  # includes timeouts
                last_exc = exc
                if attempt == MAX_ATTEMPTS:
                    break
                self._sleep(BACKOFF_BASE ** (attempt - 1))
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                last_exc = FetchError(f"{url} returned HTTP {resp.status_code}")
                if attempt == MAX_ATTEMPTS:
                    break
                delay = BACKOFF_BASE ** (attempt - 1)
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        pass
                self._sleep(delay)
                continue
            return resp
        raise FetchError(f"{url} failed after {MAX_ATTEMPTS} attempts: {last_exc}")

    def _download(self, url: str) -> tuple[httpx.Response, str]:
        client, owned = self._get_client()
        try:
            current = url
            for _ in range(MAX_REDIRECTS + 1):
                resp = self._request_with_retries(client, current)
                if resp.is_redirect:
                    location = resp.headers.get("Location")
                    if not location:
                        raise FetchError(f"{current} redirected without a Location header")
                    current = urljoin(current, location)
                    check_url_policy(current)  # reject before spending a request
                    continue
                if resp.status_code != 200:
                    raise FetchError(f"{current} returned HTTP {resp.status_code}")
                return resp, current
            raise FetchError(f"{url} exceeded {MAX_REDIRECTS} redirects")
        finally:
            if owned:
                client.close()

    # -- public ----------------------------------------------------------
    def fetch(self, url: str, *, suffix: str | None = None) -> Path:
        check_url_policy(url)  # policy first, even for cached URLs
        cached = self._find_cached(url)
        if cached is not None:
            return cached
        if os.environ.get(ENV_FLAG) != "1":
            raise FetchDisabledError(
                f"{url} is not cached in data/raw/. Network fetching runs in the CI "
                f"data-build job; set {ENV_FLAG}=1 to allow it."
            )
        resp, final_url = self._download(url)
        body = resp.content
        content_type = resp.headers.get("content-type")
        directory, digest = self._stem(url)
        directory.mkdir(parents=True, exist_ok=True)
        ext = suffix if suffix is not None else _guess_ext(content_type)
        if ext and not ext.startswith("."):
            ext = "." + ext
        target = directory / (digest + ext)
        meta = {
            "url": url,
            "final_url": final_url,
            "status": resp.status_code,
            "content_type": content_type,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        }
        # Meta first, body last: the body's existence marks a complete cache entry.
        self._atomic_write(directory / (target.name + ".meta.json"), json.dumps(meta, indent=2).encode())
        self._atomic_write(target, body)
        return target

    @staticmethod
    def _atomic_write(dest: Path, data: bytes) -> None:
        fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=dest.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, dest)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


default_fetcher = Fetcher()


def fetch(url: str, *, suffix: str | None = None) -> Path:
    """Fetch ``url`` via the module-level default :class:`Fetcher`."""
    return default_fetcher.fetch(url, suffix=suffix)
