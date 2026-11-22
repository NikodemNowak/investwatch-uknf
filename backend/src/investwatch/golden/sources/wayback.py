"""Archived pages of KNF-warned entities from the Internet Archive Wayback Machine.

Websites of entities on the KNF warning list (`knf_warnings.py`) are usually gone; the
Wayback Machine keeps public snapshots. We query the documented CDX API for HTML captures with
status 200 of each warned domain's home page and Polish home page (`/pl/`), pick one capture
and fetch its original bytes (`id_` URLs, no toolbar).

Terms: Internet Archive Terms of Use (https://archive.org/about/terms.php) grant access "for
scholarship and research purposes"; web.archive.org has no robots.txt restrictions; we send an
honest User-Agent and keep >= 1.5 s between requests. The page texts were published by the
warned entities themselves; we keep only the visible text needed for text-and-data mining
(art. 26^3 Polish Copyright Act) and remove any item on request.

Usage (from `backend/`; ~4 requests per domain):
    uv run python -m investwatch.golden.sources.wayback --max-domains 400
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict

from investwatch.collectors.html_text import html_lang, html_to_text
from investwatch.golden.sources.http import PoliteClient
from investwatch.golden.sources.knf_warnings import SNAPSHOT, WarningEntity, load_snapshot

log = logging.getLogger(__name__)

CDX = "https://web.archive.org/cdx/search/cdx"
LICENCE = (
    "Internet Archive Terms of Use (scholarship and research); page text (c) its publisher, "
    "kept for text-and-data mining (art. 26^3 pr. aut.)"
)
SECTIONS = frozenset(
    {
        "investment_services",
        "investment_firm_agent",
        "investment_funds",
        "public_offering",
        "crowdfunding",
    }
)
"""Warning-list sections whose web pages are investment offers (M3 / M2 material)."""
MIN_CHARS = 300
BACKOFF_S = (15.0, 45.0, 120.0)
"""Waits after a 429 / 503 from the CDX server before giving up on a domain."""


class Candidate(BaseModel):
    """An archived page of a warned entity, waiting for a label."""

    model_config = ConfigDict(extra="forbid")

    ref: str
    domain: str
    entity: str
    section: str
    art69_points: list[int]
    original_url: str
    archive_url: str
    timestamp: str
    retrieved_at: str
    lang: str | None
    text: str


def captures(client: PoliteClient, url: str) -> list[str]:
    """Timestamps of HTML captures of exactly `url` that returned status 200."""
    query = (
        f"{CDX}?url={quote(url)}&output=json&fl=timestamp"
        "&filter=statuscode:200&filter=mimetype:text/html&limit=200"
    )
    resp = client.get(query)
    for wait in BACKOFF_S:
        if resp.status_code not in (429, 503):
            break
        log.info("cdx %s for %s, waiting %.0f s", resp.status_code, url, wait)
        time.sleep(wait)
        resp = client.get(query)
    if resp.status_code != 200 or not resp.text.strip():
        return []
    return [row[0] for row in resp.json()[1:]]


def pick_capture(timestamps: list[str]) -> str | None:
    """A capture a third into the capture history.

    Early enough to show the live offer, not the parked or seized page that often follows a
    KNF warning.
    """
    if not timestamps:
        return None
    return sorted(timestamps)[len(timestamps) // 3]


def paths_tried(domain: str) -> list[str]:
    """Home page, then the Polish home page (warned sites target Polish clients)."""
    return [f"{domain}/", f"{domain}/pl/"]


def fetch_snapshot(client: PoliteClient, ts: str, original: str) -> tuple[str, str] | None:
    """(archive URL, HTML) of one capture, original bytes without the Wayback toolbar."""
    archive = f"https://web.archive.org/web/{ts}id_/{original}"
    try:
        resp = client.get(archive)
    except httpx.HTTPError as exc:
        log.info("fail %s: %s", archive, exc)
        return None
    ctype = resp.headers.get("content-type", "")
    if resp.status_code != 200 or "html" not in ctype:
        return None
    return f"https://web.archive.org/web/{ts}/{original}", resp.text


def candidates_for(client: PoliteClient, entity: WarningEntity, domain: str) -> list[Candidate]:
    """Archived, text-bearing pages of one warned domain."""
    out: list[Candidate] = []
    now = datetime.now(UTC).strftime("%Y-%m-%d")
    for original in paths_tried(domain):
        try:
            ts = pick_capture(captures(client, original))
        except (httpx.HTTPError, ValueError) as exc:
            log.info("cdx fail %s: %s", original, exc)
            continue
        if ts is None:
            continue
        got = fetch_snapshot(client, ts, original)
        if got is None:
            continue
        archive, html = got
        text = html_to_text(html)
        if len(text) < MIN_CHARS:
            continue
        path = urlsplit(original).path.strip("/") or "home"
        out.append(
            Candidate(
                ref=f"wayback:{domain}:{ts}:{path}"[:160],
                domain=domain,
                entity=entity.name,
                section=entity.section,
                art69_points=entity.art69_points,
                original_url=original,
                archive_url=archive,
                timestamp=ts,
                retrieved_at=now,
                lang=html_lang(html),
                text=text[:20000],
            )
        )
    return out


def main() -> None:
    """Write `data/golden/public/_candidates/wayback.jsonl` (git-ignored)."""
    parser = argparse.ArgumentParser(description=__doc__)
    repo = Path(__file__).resolve().parents[5]
    parser.add_argument("--registry", type=Path, default=repo / "data" / "registry" / SNAPSHOT)
    parser.add_argument(
        "--out", type=Path, default=repo / "data/golden/public/_candidates/wayback.jsonl"
    )
    parser.add_argument("--max-domains", type=int, default=400)
    parser.add_argument("--interval", type=float, default=1.5)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    snap = load_snapshot(args.registry)
    pairs = [
        (e, d)
        for e in sorted(snap.entities, key=lambda e: not e.advisory)
        if e.section in SECTIONS
        for d in e.domains
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.out.exists():
        done = {json.loads(line)["domain"] for line in args.out.read_text().splitlines() if line}
    client = PoliteClient(min_interval_s=args.interval)
    with args.out.open("a", encoding="utf-8") as fh:
        for entity, domain in pairs[: args.max_domains]:
            if domain in done:
                continue
            found = candidates_for(client, entity, domain)
            log.info("%s: %d pages", domain, len(found))
            for cand in found:
                fh.write(cand.model_dump_json() + "\n")
            fh.flush()
            done.add(domain)
    client.close()


if __name__ == "__main__":
    main()
