from __future__ import annotations

import gzip
import json

import pytest

from bom_html import cc_index_lines, cdx_json, warc_record
from boffo_etl import archives


def test_wayback_cdx_url_and_parse():
    url = archives.wayback_cdx_url("https://www.boxofficemojo.com/weekend/2020W01/", start="20200106", to="202611")
    assert url.startswith("https://web.archive.org/cdx/search/cdx?url=https%3A%2F%2Fwww.boxofficemojo.com")
    assert "from=20200106" in url and "to=202611" in url and "filter=statuscode%3A200" in url
    assert "from=" not in archives.wayback_cdx_url("x")
    caps = archives.parse_wayback_cdx(cdx_json([("20200113000000", "https://www.boxofficemojo.com/weekend/2020W01/")]))
    assert len(caps) == 1 and caps[0].ts14 == "20200113000000" and caps[0].status == 200
    assert archives.wayback_raw_url(caps[0]) == (
        "https://web.archive.org/web/20200113000000id_/https://www.boxofficemojo.com/weekend/2020W01/")
    assert archives.wayback_view_url(caps[0]).endswith("/web/20200113000000/https://www.boxofficemojo.com/weekend/2020W01/")
    assert archives.parse_wayback_cdx(b"[]") == [] and archives.parse_wayback_cdx(b"") == []


@pytest.mark.parametrize("body", [b"<html>Temporarily Offline</html>", b'{"a": 1}', b'["x"]'])
def test_wayback_cdx_rejects_non_answers(body):
    with pytest.raises(ValueError):
        archives.validate_wayback_cdx(body)


def test_collinfo_and_cc_index():
    body = json.dumps([
        {"id": "CC-MAIN-2017-09", "from": "2017-02-18T00:00:00", "to": "2017-03-01T00:00:00",
         "cdx-api": "https://index.commoncrawl.org/CC-MAIN-2017-09-index"},
        {"id": "CC-MAIN-2016-50", "from": "2016-12-01T00:00:00", "to": "2016-12-12T00:00:00",
         "cdx-api": "https://index.commoncrawl.org/CC-MAIN-2016-50-index"},
    ]).encode()
    crawls = archives.parse_collinfo(body)
    assert [c.id for c in crawls] == ["CC-MAIN-2016-50", "CC-MAIN-2017-09"]
    url = archives.cc_index_url(crawls[1], "https://www.boxofficemojo.com/weekend/2017W05/")
    assert url == ("https://index.commoncrawl.org/CC-MAIN-2017-09-index?url=https%3A%2F%2Fwww.boxofficemojo.com"
                   "%2Fweekend%2F2017W05%2F&output=json")
    assert archives.cc_collinfo_url("202611") == "https://index.commoncrawl.org/collinfo.json?refresh=202611"
    recs = archives.parse_cc_index(cc_index_lines([{"timestamp": "20170219000000", "url": "u", "status": "200",
                                                    "mime": "text/html", "filename": "f.warc.gz",
                                                    "offset": "37", "length": "900"}]))
    assert (recs[0].filename, recs[0].offset, recs[0].length) == ("f.warc.gz", 37, 900)
    assert archives.parse_cc_index(b'{"message": "No Captures found for: x"}\n') == []
    with pytest.raises(ValueError):
        archives.validate_cc_index(b"<html><head><title>504 Gateway Time-out</title></head></html>")
    with pytest.raises(ValueError):
        archives.validate_collinfo(b"<html></html>")


@pytest.mark.parametrize("kw", [{}, {"gzip_body": True}, {"chunked": True}, {"gzip_body": True, "chunked": True}])
def test_parse_warc_record(kw):
    status, headers, body = archives.parse_warc_record(warc_record("<html>café</html>", **kw))
    assert status == 200 and headers["content-type"].startswith("text/html")
    assert archives.decode_html(body) == "<html>café</html>"


def test_parse_warc_record_rejects_other_records():
    with pytest.raises(ValueError):
        archives.parse_warc_record(gzip.compress(b"WARC/1.0\r\nWARC-Type: request\r\n\r\nGET / HTTP/1.1\r\n\r\n"))
    with pytest.raises(OSError):
        archives.parse_warc_record(b"not gzip")


def test_decode_html_falls_back_to_windows_1252():
    assert archives.decode_html("café".encode("windows-1252")) == "café"
