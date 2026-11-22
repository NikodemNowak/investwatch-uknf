"""The "check URL" collector: one page fetched over HTTP by the compliant fetcher, text extracted.

The rendered variant is `WebCollector(name="manual")`; this one is the fast path.
"""

from __future__ import annotations

from investwatch.collectors.base import PoliteFetcher, domain_of
from investwatch.collectors.html_text import html_lang, html_to_text
from investwatch.collectors.imports.analyst import submission_item
from investwatch.collectors.schemas import CollectedItem
from investwatch.pipeline.dedup import canonical_url


class ManualCollector:
    """Fetches a single URL submitted by an analyst."""

    name = "manual"

    def __init__(self, fetcher: PoliteFetcher | None = None) -> None:
        """Use `fetcher` (tests inject a mock transport)."""
        self._fetcher = fetcher or PoliteFetcher()

    def collect(self, target: str) -> list[CollectedItem]:
        """Fetch `target` and return one item (with `fetch_status` set on failure)."""
        result = self._fetcher.fetch(target)
        url = result.final_url or target
        canonical = canonical_url(url)
        text = html_to_text(result.html) if result.html else ""
        status = result.fetch_status
        if status == "ok" and not text:
            status = "no_text"
        domain = domain_of(url)
        return [
            CollectedItem(
                platform="web",
                collector=self.name,
                external_id=canonical,
                url=url,
                author=domain,
                author_url=f"{url.split('://', 1)[0]}://{domain}" if domain else None,
                text=text,
                lang=html_lang(result.html) if result.html else None,
                fetch_status=status,
                html=result.html or None,
            )
        ]


def text_item(text: str) -> CollectedItem:
    """Wrap pasted text (no URL) as an analyst submission so it goes through the same pipeline."""
    return submission_item(text)
