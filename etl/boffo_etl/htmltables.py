"""A small, forgiving HTML table reader (standard library only).

It keeps just what the chart parsers need: every table with its rows and
cells, each cell's text, links, ``title`` attributes and "secondary" text
(Box Office Mojo's grey sub-labels, such as "2019 re-release"), plus the
page's <title> and headings. Old Box Office Mojo pages leave cells and rows
unclosed and nest tables for layout, so a new cell or row closes the open
one, and each row belongs to the innermost open table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
SKIP = frozenset(("script", "style", "noscript", "template"))
HEADINGS = frozenset(("h1", "h2", "h3", "h4", "h5", "h6"))
SECONDARY_CLASS = "a-color-secondary"
_WS = re.compile(r"\s+")


def squash(text: str) -> str:
    return _WS.sub(" ", text).strip()


@dataclass
class Cell:
    tag: str
    attrs: dict[str, str]
    colspan: int = 1
    parts: list[str] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)  # (href, link text)
    titles: list[str] = field(default_factory=list)  # title attributes of the cell and its descendants
    secondary_parts: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return squash(" ".join(self.parts))

    @property
    def secondary(self) -> str:
        return squash(" ".join(self.secondary_parts))

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())


@dataclass
class Row:
    attrs: dict[str, str]
    cells: list[Cell] = field(default_factory=list)

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())


@dataclass
class Table:
    attrs: dict[str, str]
    depth: int
    rows: list[Row] = field(default_factory=list)

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())


@dataclass
class Page:
    title: str
    headings: list[tuple[str, str]]  # (tag, text)
    tables: list[Table]


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[Table] = []
        self._open_tables: list[dict] = []  # {"table", "row", "cell"}
        self._stack: list[tuple[str, bool]] = []  # open elements: (tag, starts secondary text)
        self._skip = 0
        self._secondary = 0
        self._link: dict | None = None
        self._title: list[str] | None = None
        self.title_parts: list[str] = []
        self._heading: tuple[str, list[str]] | None = None
        self.headings: list[tuple[str, str]] = []

    # -- helpers ---------------------------------------------------------
    def _ctx(self) -> dict | None:
        return self._open_tables[-1] if self._open_tables else None

    def _cell(self) -> Cell | None:
        ctx = self._ctx()
        return ctx["cell"] if ctx else None

    def _truncate(self, depth: int) -> None:
        """Close every open element above ``depth`` (unclosed tags inside a closed cell)."""
        for _, secondary in self._stack[depth:]:
            if secondary:
                self._secondary -= 1
        del self._stack[depth:]

    def _close_cell(self, ctx: dict) -> None:
        if ctx["cell"] is not None:
            self._truncate(ctx["cell_depth"])
            ctx["cell"] = None
            if self._link is not None and all(c["cell"] is not self._link["cell"] for c in self._open_tables):
                self._end_link()  # an <a> left open when its cell closed

    def _close_row(self, ctx: dict) -> None:
        self._close_cell(ctx)
        if ctx["row"] is not None:
            self._truncate(ctx["row_depth"])
            ctx["row"] = None

    def _end_link(self) -> None:
        link = self._link
        link["cell"].links.append((link["href"], squash(" ".join(link["parts"]))))
        self._link = None

    def _pop(self, tag: str) -> None:
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                self._truncate(i)
                return

    # -- parser callbacks ------------------------------------------------
    def handle_starttag(self, tag, attrs):  # noqa: C901 - a flat dispatch reads best here
        a = {k: (v or "") for k, v in attrs}
        if tag in SKIP:
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "title":
            self._title = []
        elif tag in HEADINGS:
            self._heading = (tag, [])
        if tag == "table":
            self._open_tables.append({"table": Table(a, len(self._open_tables)), "row": None, "cell": None,
                                      "depth": len(self._stack), "row_depth": 0, "cell_depth": 0})
            self.tables.append(self._open_tables[-1]["table"])
        elif tag == "tr":
            ctx = self._ctx()
            if ctx is not None:
                self._close_row(ctx)
                ctx["row"] = Row(a)
                ctx["row_depth"] = len(self._stack)
                ctx["table"].rows.append(ctx["row"])
        elif tag in ("td", "th"):
            ctx = self._ctx()
            if ctx is not None:
                self._close_cell(ctx)
                if ctx["row"] is None:  # a cell outside any <tr>
                    ctx["row"] = Row({})
                    ctx["row_depth"] = len(self._stack)
                    ctx["table"].rows.append(ctx["row"])
                try:
                    span = max(1, int(a.get("colspan", "1") or 1))
                except ValueError:
                    span = 1
                ctx["cell"] = Cell(tag, a, colspan=span)
                ctx["cell_depth"] = len(self._stack)
                ctx["row"].cells.append(ctx["cell"])
        cell = self._cell()
        if cell is not None:
            if a.get("title"):
                cell.titles.append(a["title"])
            if tag == "a" and "href" in a:
                self._link = {"href": a["href"], "parts": [], "cell": cell}
            elif tag == "br":
                cell.parts.append(" ")
        if tag in VOID:
            return
        secondary = SECONDARY_CLASS in a.get("class", "").split()
        if secondary:
            self._secondary += 1
        self._stack.append((tag, secondary))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in SKIP:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag == "title" and self._title is not None:
            self.title_parts.extend(self._title)
            self._title = None
        elif tag in HEADINGS and self._heading is not None and self._heading[0] == tag:
            self.headings.append((tag, squash(" ".join(self._heading[1]))))
            self._heading = None
        if tag == "a" and self._link is not None:
            self._end_link()
        ctx = self._ctx()
        if tag == "table":
            if ctx is not None:
                self._close_row(ctx)
                self._truncate(ctx["depth"])
                self._open_tables.pop()
            return
        if tag == "tr":
            if ctx is not None:
                self._close_row(ctx)
            return
        if tag in ("td", "th"):
            if ctx is not None:
                self._close_cell(ctx)
            return
        self._pop(tag)

    def handle_data(self, data):
        if self._skip:
            return
        if self._title is not None:
            self._title.append(data)
        if self._heading is not None:
            self._heading[1].append(data)
        cell = self._cell()
        if cell is None:
            return
        cell.parts.append(data)
        if self._secondary:
            cell.secondary_parts.append(data)
        if self._link is not None and self._link["cell"] is cell:
            self._link["parts"].append(data)


def parse(html: str) -> Page:
    b = _Builder()
    b.feed(html)
    b.close()
    return Page(title=squash(" ".join(b.title_parts)), headings=b.headings, tables=b.tables)
