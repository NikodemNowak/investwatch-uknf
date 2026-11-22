"""Visible text of an HTML page, header and footer included.

Main-content extractors (trafilatura, readability) drop headers and footers, which is exactly
where firm identification, "materiał marketingowy" labels and risk warnings live. Compliance
rules need the whole page; whether a block is *visible* is the render check's job.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

_SPACE = re.compile(r"\s+")
_SKIP = {"script", "style", "head", "noscript", "template", "svg"}
_BLOCK = {
    "address", "article", "aside", "blockquote", "br", "dd", "details", "div", "dl", "dt",
    "figcaption", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li",
    "main", "nav", "ol", "p", "pre", "section", "summary", "table", "td", "th", "tr", "ul",
}  # fmt: skip


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP:
            self._skip += 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(_SPACE.sub(" ", data))


def html_to_text(html: str) -> str:
    """Return one line per block element, whitespace collapsed, empty lines dropped."""
    parser = _TextParser()
    parser.feed(html)
    parser.close()
    lines = (line.strip() for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


def html_lang(html: str) -> str | None:
    """Return the `<html lang>` attribute, normalised to two letters."""
    match = re.search(r"<html[^>]*\blang=[\"']?([a-zA-Z]{2})", html)
    return match.group(1).lower() if match else None
