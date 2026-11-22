"""Canonical URLs, content hashes and render (layout) hashes.

An exact duplicate has the same `content_hash` *and* the same `render_hash`: rules 4-8 and 13
depend on the layout only, so two pages with the same text can deserve different verdicts.
Posts without a render (social items, pasted text) have `render_hash = None` and compare by
text alone. A duplicate never replaces a location: it joins the original's occurrence group.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from investwatch.collectors.schemas import CollectedItem
from investwatch.core.schemas import Post, PostProvenance, RenderSnapshot

_TRACKING_PARAMS = {"fbclid", "gclid", "dclid", "msclkid", "igshid", "mc_cid", "mc_eid", "ref"}
_SPACE = re.compile(r"\s+")


def canonical_url(url: str) -> str:
    """Drop tracking parameters and the fragment, lowercase scheme and host."""
    if "://" not in url:
        return url
    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    ]
    path = parts.path or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(sorted(query)), "")
    )


def normalize_text(text: str) -> str:
    """Normalise text for hashing: NFKC, casefold, collapsed whitespace."""
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", text).casefold()).strip()


def content_hash(text: str) -> str:
    """Return sha256 of the normalised text."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def render_hash(render: RenderSnapshot | None) -> str | None:
    """sha256 of the layout, or None without a render.

    Per viewport: every block's text hash, font size (1 px), colours and visibility flags.
    """
    if render is None or not any(render.viewports.values()):
        return None
    digest = hashlib.sha256()
    for viewport in sorted(render.viewports):
        digest.update(f"[{viewport}]".encode())
        for b in render.viewports[viewport]:
            text = hashlib.sha256(normalize_text(b.text).encode("utf-8")).hexdigest()[:16]
            flags = "".join(
                "1" if f else "0"
                for f in (b.visible, b.occluded, b.clipped, b.in_footer, b.in_collapsed)
            )
            line = f"{text}|{round(b.font_px)}|{b.color}|{b.background}|{flags}\n"
            digest.update(line.encode())
    return digest.hexdigest()


FICTIONAL_HOSTS = frozenset({"demo-sites"})
"""Hosts that serve only fictional demo pages (`demo-sites` container)."""


def _fictional_host(url: str | None) -> bool:
    host = (urlsplit(url).hostname or "").lower() if url and "://" in url else ""
    return host in FICTIONAL_HOSTS or host.endswith(".example") or host == "example"


def post_provenance(item: CollectedItem) -> PostProvenance:
    """How `item` was obtained, from its raw envelope; flags fictional demo material.

    Synthetic: an import row marked `synthetic`, a page of the demo-sites container, a `.example`
    domain (reserved for fictional firms), or a fixture replayed without an envelope.
    """
    raw = item.raw or {}
    synthetic = (
        bool(raw.get("synthetic"))
        or _fictional_host(item.url)
        or _fictional_host(item.author_url)
        or (item.collector == "sample" and item.raw is None)
    )
    fetched = raw.get("fetched_at")
    try:
        fetched_at = datetime.fromisoformat(str(fetched)) if fetched else None
    except ValueError:
        fetched_at = None
    from investwatch.collectors.policy import access_mode_of, legal_basis_of

    note = raw.get("provenance_note") or raw.get("note")
    return PostProvenance(
        access_mode=str(raw.get("access_mode") or access_mode_of(item.collector)),
        legal_basis=str(raw.get("legal_basis") or legal_basis_of(item.collector)),
        fetched_at=fetched_at,
        synthetic=synthetic,
        note=str(note)[:500] if note else None,
        fetch_error=item.error[:500] if item.error else None,
    )


def to_post(item: CollectedItem, now: datetime | None = None) -> Post:
    """Turn a collected item into a contract `Post` (ids, canonical URL, hash, timestamps)."""
    seen = now or datetime.now(UTC)
    return Post(
        id=item.post_id or uuid.uuid4(),
        platform=item.platform,
        collector=item.collector,
        external_id=item.external_id,
        url=item.url,
        canonical_url=canonical_url(item.url),
        author=item.author,
        author_url=item.author_url,
        text=item.text,
        lang=item.lang,
        content_hash=content_hash(item.text),
        html_key=None,
        render_key=None,
        screenshot_keys={},
        published_at=item.published_at,
        first_seen_at=seen,
        last_seen_at=seen,
        fetch_status=item.fetch_status,
        provenance=post_provenance(item),
    )
