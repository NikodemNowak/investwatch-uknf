"""Group findings by the entity they concern and merge them into one object per entity."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit
from uuid import UUID

from investwatch.core.schemas import ModuleId, Platform, RegisteredFirm, RiskLevel
from investwatch.db.schemas import FindingView
from investwatch.entities.schemas import EntityDetail, EntityKind, EntitySummary, RegisterState

MODULES: tuple[ModuleId, ...] = ("m1_third_party_ad", "m2_risk_disclosure", "m3_shadow_advisory")
RISK_RANK: dict[RiskLevel, int] = {"low": 1, "medium": 2, "high": 3}
OPEN = ("new", "in_review")
_SPACES = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")


def normalize_name(name: str) -> str:
    """Key form of a publisher name: case-folded, no leading `@`, single spaces."""
    return _SPACES.sub(" ", name.strip().lstrip("@").casefold()).strip()


def _domain(url: str) -> str:
    host = urlsplit(url).hostname or ""
    return host.removeprefix("www.")


def _known(name: str | None) -> bool:
    """A real name, not empty and not a placeholder such as "(wklejony tekst)"."""
    text = (name or "").strip()
    return bool(normalize_name(text)) and not (text.startswith("(") and text.endswith(")"))


def _publisher(f: FindingView) -> str:
    """Who published the material: the model's advertiser, the post author or the domain.

    Pasted text has no publisher; such findings belong to no entity unless a firm matched.
    """
    for candidate in (f.advertiser, f.post.author, _domain(f.post.url)):
        if candidate and _known(candidate):
            return candidate.strip()
    return ""


def firm_name_key(name: str) -> str:
    """Firm name without case and punctuation: "Finax, o.c.p., a.s." == "Finax o.c.p., a.s."."""
    return " ".join(_PUNCT.sub(" ", name.casefold()).split())


class _Firms:
    """Which firm entity a finding belongs to, with one key per firm.

    The registered firm id is the key. Two register records of one legal entity (a branch and
    the same firm's cross-border notification) share the smallest id. A finding without a firm
    match whose publisher also published material matched to a firm as its author (the M3 or
    unmatched M2 finding of "X-Trade Brokers DM S.A. (XTB)" next to its M2 finding on xtb.com)
    joins that firm instead of becoming a second entity under a different name.
    """

    def __init__(self, findings: Sequence[FindingView]) -> None:
        firms: dict[str, list[RegisteredFirm]] = {}
        for f in findings:
            if f.firm is not None:
                firms.setdefault(firm_name_key(f.firm.name), []).append(f.firm)
        self.canonical: dict[str, RegisteredFirm] = {
            k: min(group, key=lambda firm: str(firm.id)) for k, group in firms.items()
        }
        self.by_publisher: dict[str, RegisteredFirm] = {}
        for f in sorted(findings, key=lambda f: str(f.id)):
            if f.firm is not None and f.firm_match is not None and f.firm_match.on == "author":
                publisher = normalize_name(_publisher(f))
                if publisher:
                    self.by_publisher.setdefault(publisher, self.of(f.firm))

    def of(self, firm: RegisteredFirm) -> RegisteredFirm:
        """The firm record that keys this firm's entity."""
        return self.canonical.get(firm_name_key(firm.name), firm)


def entity_refs(f: FindingView, firms: _Firms | None = None) -> list[tuple[str, EntityKind, str]]:
    """Entities a finding belongs to, as `(key, kind, display name)`.

    A firm match owns the finding. An M1 finding also belongs to the third party that ran the
    ad, so the influencer's card shows every firm it promoted; without a firm the publisher is
    the entity (M3 shadow advisers, unmatched M2 material) unless it is known to publish for a
    registered firm.
    """
    firms = firms or _Firms([f])
    refs: list[tuple[str, EntityKind, str]] = []
    if f.firm is not None:
        firm = firms.of(f.firm)
        refs.append((f"firm:{firm.id}", "firm", firm.name))
    publisher = _publisher(f)
    if publisher and (f.firm is None or f.module == "m1_third_party_ad"):
        norm = normalize_name(publisher)
        owner = firms.by_publisher.get(norm) if f.firm is None else None
        if owner is not None:
            refs.append((f"firm:{owner.id}", "firm", owner.name))
        elif f.firm is None or norm != normalize_name(f.firm.name):
            refs.append((f"name:{norm}", "advertiser", publisher))
    return refs


def _merge(
    key: str,
    kind: EntityKind,
    name: str,
    findings: Sequence[FindingView],
    firm_sources: Mapping[UUID, str],
) -> EntitySummary:
    firm = next((f.firm for f in findings if kind == "firm" and f.firm is not None), None)
    if firm is not None and key.startswith("firm:"):
        firm = next((f.firm for f in findings if f.firm and f"firm:{f.firm.id}" == key), firm)
    register: RegisterState = "absent"
    if firm is not None:
        register = "knf" if firm_sources.get(firm.id, "knf") == "knf" else "fictional"
    latest = max(findings, key=lambda f: (f.created_at, f.score))
    platforms: list[Platform] = []
    first_seen = []
    last_seen = []
    occurrences = 0
    for f in findings:
        group = f.occurrences or []
        occurrences += max(1, len(group))
        for p in [f.post.platform, *(o.platform for o in group)]:
            if p not in platforms:
                platforms.append(p)
        first_seen.append(f.first_seen_at or f.post.first_seen_at)
        last_seen.append(f.last_seen_at or f.post.last_seen_at)
    return EntitySummary(
        key=key,
        kind=kind,
        name=name,
        firm=firm,
        knf_register=register,
        knf_warning=next((f.knf_warning for f in findings if f.knf_warning), None),
        modules={m: sum(1 for f in findings if f.module == m) for m in MODULES},
        total=len(findings),
        open=sum(1 for f in findings if f.status in OPEN),
        confirmed=sum(1 for f in findings if f.status == "confirmed"),
        dismissed=sum(1 for f in findings if f.status == "dismissed"),
        highest_risk=max((f.risk_level for f in findings), key=RISK_RANK.__getitem__),
        max_score=max(f.score for f in findings),
        occurrences=occurrences,
        platforms=platforms,
        first_seen_at=min(first_seen),
        last_seen_at=max(last_seen),
        latest_finding_id=latest.id,
        latest_at=latest.created_at,
    )


def _groups(
    findings: Sequence[FindingView],
) -> dict[str, tuple[EntityKind, str, list[FindingView]]]:
    groups: dict[str, tuple[EntityKind, str, list[FindingView]]] = {}
    firms = _Firms(findings)
    for f in findings:
        for key, kind, name in entity_refs(f, firms):
            groups.setdefault(key, (kind, name, []))[2].append(f)
    return groups


def _rank(e: EntitySummary) -> tuple[int, int, int, str]:
    return (RISK_RANK[e.highest_risk], e.open, e.total, e.latest_at.isoformat())


def aggregate(
    findings: Sequence[FindingView], firm_sources: Mapping[UUID, str]
) -> list[EntitySummary]:
    """One summary per entity, most serious first (risk, open findings, total, newest)."""
    entities = [
        _merge(key, kind, name, group, firm_sources)
        for key, (kind, name, group) in _groups(findings).items()
    ]
    return sorted(entities, key=_rank, reverse=True)


def entity_detail(
    findings: Sequence[FindingView], firm_sources: Mapping[UUID, str], key: str
) -> EntityDetail | None:
    """The entity `key` with its findings, newest first; None when no finding belongs to it."""
    group = _groups(findings).get(key)
    if group is None:
        return None
    kind, name, own = group
    summary = _merge(key, kind, name, own, firm_sources)
    ordered = sorted(own, key=lambda f: f.created_at, reverse=True)
    return EntityDetail(**summary.model_dump(), findings=ordered)


def matches_name(entity: EntitySummary, query: str) -> bool:
    """Case-insensitive search over the entity name and its firm's aliases and domains."""
    needle = normalize_name(query)
    if not needle:
        return True
    names = [entity.name]
    if entity.firm is not None:
        names += [*entity.firm.aliases, *entity.firm.domains, *entity.firm.handles]
    return any(needle in normalize_name(n) for n in names)
