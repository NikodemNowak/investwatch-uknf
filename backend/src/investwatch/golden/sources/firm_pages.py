"""Marketing pages of KNF-registered investment firms, from the firms' own websites.

Real M2 material (and tricky negatives for M3: licensed firms): each firm's Polish landing
page plus a few same-site pages whose link text or path suggests an offer, a promotion or
performance figures. robots.txt is honoured for the `InvestWatchBot` token, the User-Agent is
honest, at most `--per-firm` pages per site and >= 3 s between requests to one host. A site
that refuses us (robots, 401/403/429) is skipped, never retried another way.

Usage (from `backend/`):
    uv run python -m investwatch.golden.sources.firm_pages
"""

from __future__ import annotations

import argparse
import logging
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict

from investwatch.collectors.html_text import html_lang, html_to_text
from investwatch.golden.sources.http import PoliteClient, RobotsDisallowedError

log = logging.getLogger(__name__)

LICENCE = (
    "Page text (c) the firm; public marketing material fetched robots-respecting for "
    "text-and-data mining (art. 26^3 pr. aut.); no TDM reservation found"
)

FIRMS: tuple[tuple[str, str], ...] = (
    ("X-Trade Brokers DM S.A. (XTB)", "https://www.xtb.com/pl/oferta"),
    ("mBank S.A. (eMakler)", "https://www.mbank.pl/indywidualny/inwestycje/"),
    ("Dom Maklerski BOŚ S.A. (bossa.pl)", "https://bossa.pl/oferta"),
    ("PKO BP (Biuro Maklerskie)", "https://www.bm.pkobp.pl/"),
    (
        "Santander Bank Polska (Santander BM)",
        "https://www.santander.pl/klient-indywidualny/inwestycje",
    ),
    (
        "Bank Pekao (Biuro Maklerskie Pekao)",
        "https://www.pekao.com.pl/klient-indywidualny/inwestycje.html",
    ),
    ("Noble Securities S.A.", "https://noblesecurities.pl/"),
    ("Michael / Ström Dom Maklerski S.A.", "https://michaelstrom.pl/"),
    ("Trigon Dom Maklerski S.A.", "https://www.trigon.pl/"),
    ("Dom Maklerski Navigator S.A.", "https://www.dmnavigator.pl/"),
    ("Ipopema Securities S.A.", "https://www.ipopemasecurities.pl/"),
    ("Saxo Bank A/S", "https://www.home.saxo/pl-pl"),
    ("IG Europe GmbH", "https://www.ig.com/pl"),
    ("Admirals Europe Ltd", "https://admiralmarkets.com/pl"),
    ("CMC Markets Germany GmbH", "https://www.cmcmarkets.com/pl-pl/"),
    ("Plus500 CY Ltd", "https://www.plus500.com/pl/"),
    ("eToro (Europe) Ltd", "https://www.etoro.com/pl/"),
    ("Trading 212 Markets Ltd", "https://www.trading212.com/pl"),
    ("Capital Com SV Investments Ltd", "https://capital.com/pl"),
    ("Freedom Finance Europe Ltd (Freedom24)", "https://freedom24.com/pl"),
    ("Interactive Brokers Ireland Ltd", "https://www.interactivebrokers.ie/pl/home.php"),
    ("Finax o.c.p., a.s.", "https://www.finax.eu/pl"),
    ("Swissquote Bank Europe SA", "https://pl.swissquote.com/"),
    ("Pepperstone EU Ltd", "https://pepperstone.com/pl-pl/"),
    ("Revolut Securities Europe UAB", "https://www.revolut.com/pl-PL/trading/"),
    ("Dom Maklerski Banku Handlowego S.A.", "https://www.dmbh.pl/"),
    (
        "Biuro Maklerskie mBanku (mTFI / eMakler)",
        "https://www.mbank.pl/indywidualny/inwestycje/emakler/",
    ),
    ("Dom Maklerski Banku Ochrony Środowiska (IKE)", "https://bossa.pl/oferta/ike-ikze"),
    ("Quercus TFI (dystrybucja)", "https://www.quercustfi.pl/"),
    ("Investors TFI", "https://investors.pl/"),
)
"""(firm as in the KNF registers or its brand, start URL). Start URLs are public landing pages."""

KEYWORDS = re.compile(
    r"promocj|bonus|nagrod|oferta|ike|ikze|etf|obligacj|lokat|zysk|stop[aey] zwrotu|"
    r"wynik|rentown|oprocentowan|portfel|robo|plan|oszczędz|inwestuj|konto|cfd|akcje|"
    r"kryptowalut|fundusz|subskrypc|emisj",
    re.I,
)
MIN_CHARS = 400


class FirmPage(BaseModel):
    """A fetched firm page, waiting for a label."""

    model_config = ConfigDict(extra="forbid")

    ref: str
    firm: str
    url: str
    retrieved_at: str
    lang: str | None
    text: str


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)


def offer_links(html: str, base: str, limit: int) -> list[str]:
    """Same-host links whose text or path looks like an offer, best first."""
    parser = _Links()
    parser.feed(html)
    host = urlsplit(base).netloc
    scored: dict[str, int] = {}
    for href, text in parser.links:
        url = urljoin(base, href).split("#")[0]
        parts = urlsplit(url)
        if parts.netloc != host or parts.query or not parts.scheme.startswith("http"):
            continue
        if re.search(r"\.(pdf|jpe?g|png|zip)$|login|logowanie|rejestr|kontakt|kariera", url, re.I):
            continue
        score = len(KEYWORDS.findall(f"{text} {parts.path}"))
        if score and url.rstrip("/") != base.rstrip("/"):
            scored[url] = max(scored.get(url, 0), score)
    return sorted(scored, key=lambda u: (-scored[u], len(u)))[:limit]


def page(client: PoliteClient, firm: str, url: str) -> tuple[FirmPage | None, str]:
    """Fetch one page; (page or None, raw HTML)."""
    try:
        resp = client.get(url)
    except RobotsDisallowedError:
        log.info("robots.txt disallows %s", url)
        return None, ""
    except httpx.HTTPError as exc:
        log.info("fail %s: %s", url, exc)
        return None, ""
    if resp.status_code != 200 or "html" not in resp.headers.get("content-type", ""):
        log.info("skip %s: HTTP %s", url, resp.status_code)
        return None, ""
    if re.search(r'name=["\']tdm-reservation["\'][^>]*content=["\']1', resp.text, re.I) or (
        resp.headers.get("tdm-reservation") == "1"
    ):
        log.info("TDM reservation on %s: skipped", url)
        return None, ""
    text = html_to_text(resp.text)
    if len(text) < MIN_CHARS:
        log.info("skip %s: %d chars of text (JS-only page?)", url, len(text))
        return None, resp.text
    final = str(resp.url)
    return (
        FirmPage(
            ref=f"web:{final}"[:200],
            firm=firm,
            url=final,
            retrieved_at=datetime.now(UTC).strftime("%Y-%m-%d"),
            lang=html_lang(resp.text),
            text=text[:20000],
        ),
        resp.text,
    )


def main() -> None:
    """Write `data/golden/public/_candidates/firm_pages.jsonl` (git-ignored)."""
    parser = argparse.ArgumentParser(description=__doc__)
    repo = Path(__file__).resolve().parents[5]
    parser.add_argument(
        "--out", type=Path, default=repo / "data/golden/public/_candidates/firm_pages.jsonl"
    )
    parser.add_argument("--per-firm", type=int, default=3)
    parser.add_argument("--interval", type=float, default=3.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    client = PoliteClient(min_interval_s=args.interval)
    seen: set[str] = set()
    with args.out.open("w", encoding="utf-8") as fh:
        for firm, start in FIRMS:
            first, html = page(client, firm, start)
            urls = offer_links(html, start, args.per_firm * 2) if html else []
            got = [first] if first else []
            for url in urls:
                if len(got) >= args.per_firm:
                    break
                more, _ = page(client, firm, url)
                if more:
                    got.append(more)
            for item in got:
                if item.url not in seen:
                    seen.add(item.url)
                    fh.write(item.model_dump_json() + "\n")
            log.info("%s: %d pages", firm, len(got))
    client.close()


if __name__ == "__main__":
    main()
