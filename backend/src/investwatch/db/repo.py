"""Repository: the only place that turns ORM rows into contract models and back."""

from __future__ import annotations

import hashlib
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, get_args

from pgvector.sqlalchemy import Vector
from sqlalchemy import Select, delete, func, or_, select, type_coerce
from sqlalchemy.orm import Session

from investwatch.core.schemas import (
    Finding,
    FirmMatch,
    ModuleId,
    Platform,
    Post,
    PostProvenance,
    RegisteredFirm,
    RuleResult,
    Status,
    TrendBucket,
    TrendPoint,
    TrendSeries,
)
from investwatch.db.models import (
    EMBEDDING_DIM,
    FindingRow,
    FirmAliasRow,
    FirmRow,
    LabelRow,
    PostRow,
    RegistrySyncLogRow,
    ScrapeRunRow,
    SettingRow,
    SourceRow,
    utcnow,
)
from investwatch.db.schemas import (
    FindingFilters,
    FindingsPage,
    FindingView,
    ModuleSummary,
    Occurrence,
    ProcessingTrace,
    ScrapeRun,
    Source,
    Summary,
    Thresholds,
    UpsertResult,
)
from investwatch.registry.schemas import (
    FirmDetail,
    FirmSummary,
    KnfWarning,
    RegistryStatus,
    SyncResult,
    knf_attribution,
)

MODULES: tuple[ModuleId, ...] = get_args(ModuleId)
THRESHOLDS_KEY = "thresholds"
_ALIAS_TYPES_AS_ALIAS = ("former_name", "trade_name", "brand")


def _aware(value: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; everything we store is UTC."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _aware_req(value: datetime) -> datetime:
    result = _aware(value)
    assert result is not None
    return result


# ---------------------------------------------------------------- posts


def post_from_row(row: PostRow) -> Post:
    """Convert a post row to the contract model."""
    return Post(
        id=row.id,
        platform=row.platform,
        collector=row.collector,
        external_id=row.external_id,
        url=row.url,
        canonical_url=row.canonical_url,
        author=row.author,
        author_url=row.author_url,
        text=row.text,
        lang=row.lang,
        content_hash=row.content_hash,
        html_key=row.html_key,
        render_key=row.render_key,
        screenshot_keys=row.screenshot_keys or {},
        published_at=_aware(row.published_at),
        first_seen_at=_aware_req(row.first_seen_at),
        last_seen_at=_aware_req(row.last_seen_at),
        fetch_status=row.fetch_status,
        provenance=PostProvenance.model_validate(row.provenance) if row.provenance else None,
    )


def upsert_post(session: Session, post: Post, source_id: uuid.UUID | None = None) -> UpsertResult:
    """Insert a post or refresh the stored one with the same `(platform, external_id)`."""
    row = session.scalar(
        select(PostRow).where(
            PostRow.platform == post.platform, PostRow.external_id == post.external_id
        )
    )
    if row is None:
        row = PostRow(
            id=post.id,
            platform=post.platform,
            collector=post.collector,
            external_id=post.external_id,
            url=post.url,
            canonical_url=post.canonical_url,
            author=post.author,
            author_url=post.author_url,
            text=post.text,
            lang=post.lang,
            content_hash=post.content_hash,
            html_key=post.html_key,
            render_key=post.render_key,
            screenshot_keys={str(k): v for k, v in post.screenshot_keys.items()},
            published_at=post.published_at,
            first_seen_at=post.first_seen_at,
            last_seen_at=post.last_seen_at,
            fetch_status=post.fetch_status,
            source_id=source_id,
            provenance=post.provenance.model_dump(mode="json") if post.provenance else None,
        )
        session.add(row)
        session.flush()
        return UpsertResult(post=post_from_row(row), created=True, changed=True)

    changed = row.content_hash != post.content_hash
    row.last_seen_at = post.last_seen_at
    row.fetch_status = post.fetch_status
    row.url = post.url
    if post.provenance is not None:
        row.provenance = post.provenance.model_dump(mode="json")
    if changed:
        row.text = post.text
        row.lang = post.lang
        row.content_hash = post.content_hash
        row.author = post.author
        row.author_url = post.author_url
        row.embedding = None
        row.duplicate_of = None
        row.render_hash = None
    for attr in ("html_key", "render_key"):
        if getattr(post, attr):
            setattr(row, attr, getattr(post, attr))
    if post.screenshot_keys:
        row.screenshot_keys = {str(k): v for k, v in post.screenshot_keys.items()}
    session.flush()
    return UpsertResult(post=post_from_row(row), created=False, changed=changed)


def platform_posts(session: Session, platform: str, collector: str) -> list[tuple[uuid.UUID, str]]:
    """(id, external_id) of stored posts with text from one platform and collector."""
    rows = session.execute(
        select(PostRow.id, PostRow.external_id).where(
            PostRow.platform == platform, PostRow.collector == collector, PostRow.text != ""
        )
    )
    return [(r[0], r[1]) for r in rows]


def redact_post(session: Session, post_id: uuid.UUID) -> None:
    """Drop a post's content (source deleted it, or a retention rule expired); keep the id."""
    row = session.get(PostRow, post_id)
    if row is None:
        return
    row.text = ""
    row.fetch_status = "no_text"
    row.content_hash = hashlib.sha256(b"").hexdigest()
    row.embedding = None
    row.html_key = None


def get_post(session: Session, post_id: uuid.UUID) -> Post | None:
    """Return one post."""
    row = session.get(PostRow, post_id)
    return post_from_row(row) if row else None


def set_post_keys(
    session: Session,
    post_id: uuid.UUID,
    *,
    html_key: str | None = None,
    render_key: str | None = None,
    screenshot_keys: dict[str, str] | None = None,
    render_hash: str | None = None,
) -> None:
    """Record object-store keys (and the layout fingerprint of the render) for a post."""
    row = session.get(PostRow, post_id)
    if row is None:
        return
    if render_hash:
        row.render_hash = render_hash
    if html_key:
        row.html_key = html_key
    if render_key:
        row.render_key = render_key
    if screenshot_keys:
        row.screenshot_keys = dict(screenshot_keys)


def find_hash_duplicate(session: Session, post_id: uuid.UUID) -> uuid.UUID | None:
    """Return the earliest *earlier* post with the same normalised text and the same layout.

    Posts without a render (`render_hash` None) only match other posts without one.
    """
    row = session.get(PostRow, post_id)
    if row is None or not row.text.strip():
        return None
    same_layout = (
        PostRow.render_hash.is_(None)
        if row.render_hash is None
        else PostRow.render_hash == row.render_hash
    )
    return session.scalar(
        select(PostRow.id)
        .where(
            PostRow.content_hash == row.content_hash,
            same_layout,
            or_(
                PostRow.first_seen_at < row.first_seen_at,
                (PostRow.first_seen_at == row.first_seen_at) & (PostRow.id < post_id),
            ),
            PostRow.duplicate_of.is_(None),
            PostRow.fetch_status == "ok",
        )
        .order_by(PostRow.first_seen_at, PostRow.id)
        .limit(1)
    )


def find_near_duplicate(
    session: Session, post_id: uuid.UUID, embedding: list[float], min_cosine: float
) -> uuid.UUID | None:
    """Return the closest earlier post with cosine similarity >= `min_cosine` (Postgres only).

    Only posts without a render take part: a page's verdict depends on its layout, so near
    text is never enough to merge two rendered pages.
    """
    if session.get_bind().dialect.name != "postgresql":
        return None
    current = session.get(PostRow, post_id)
    if current is None or current.render_hash is not None:
        return None
    # The column is JSON-with-variant; coerce to get pgvector's comparator (`<=>`).
    distance = type_coerce(PostRow.embedding, Vector(EMBEDDING_DIM)).cosine_distance(embedding)
    row = session.execute(
        select(PostRow.id, distance.label("d"))
        .where(
            PostRow.id != post_id,
            PostRow.embedding.is_not(None),
            PostRow.duplicate_of.is_(None),
            PostRow.render_hash.is_(None),
        )
        .order_by(distance)
        .limit(1)
    ).first()
    if row is None or row.d is None or 1.0 - float(row.d) < min_cosine:
        return None
    found: uuid.UUID = row.id
    return found


def similar_posts(
    session: Session, post_id: uuid.UUID, limit: int = 3
) -> list[tuple[PostRow, float, uuid.UUID | None]]:
    """Nearest posts by embedding cosine (pgvector), with one finding id each; [] off Postgres."""
    if session.get_bind().dialect.name != "postgresql":
        return []
    current = session.get(PostRow, post_id)
    if current is None or current.embedding is None:
        return []
    distance = type_coerce(PostRow.embedding, Vector(EMBEDDING_DIM)).cosine_distance(
        list(current.embedding)
    )
    rows = session.execute(
        select(PostRow, distance.label("d"))
        .where(
            PostRow.id != post_id,
            PostRow.embedding.is_not(None),
            PostRow.duplicate_of.is_(None),
        )
        .order_by(distance)
        .limit(limit)
    ).all()
    ids = [row[0].id for row in rows]
    best: dict[uuid.UUID, uuid.UUID] = {}
    if ids:
        for fid, pid in session.execute(
            select(FindingRow.id, FindingRow.post_id)
            .where(FindingRow.post_id.in_(ids))
            .order_by(FindingRow.score.desc())
        ):
            best.setdefault(pid, fid)
    return [(row[0], 1.0 - float(row[1]), best.get(row[0].id)) for row in rows]


def post_row(session: Session, post_id: uuid.UUID) -> PostRow | None:
    """The stored post row (source, token count, layout hash) for read-only provenance views."""
    return session.get(PostRow, post_id)


def set_embedding(session: Session, post_id: uuid.UUID, embedding: list[float]) -> None:
    """Store the embedding of a post."""
    row = session.get(PostRow, post_id)
    if row is not None:
        row.embedding = embedding


def set_trace(
    session: Session, post_id: uuid.UUID, trace: ProcessingTrace, tokens: int | None = None
) -> None:
    """Store the processing trace (and token count, when known) of a post."""
    row = session.get(PostRow, post_id)
    if row is None:
        return
    row.trace = trace.model_dump(mode="json")
    if tokens is not None:
        row.token_count = tokens


def get_trace(session: Session, post_id: uuid.UUID) -> ProcessingTrace | None:
    """Return the processing trace of a post."""
    row = session.get(PostRow, post_id)
    return ProcessingTrace.model_validate(row.trace) if row is not None and row.trace else None


def posts_without_embedding(session: Session, limit: int = 32) -> list[Post]:
    """Return analysable posts that still have no embedding (e.g. loaded by `seed`)."""
    rows = session.scalars(
        select(PostRow)
        .where(PostRow.embedding.is_(None), PostRow.fetch_status == "ok", PostRow.text != "")
        .order_by(PostRow.first_seen_at)
        .limit(limit)
    )
    return [post_from_row(r) for r in rows]


def set_token_count(session: Session, post_id: uuid.UUID, tokens: int) -> None:
    """Store the token count of a post."""
    row = session.get(PostRow, post_id)
    if row is not None:
        row.token_count = tokens


def mark_duplicate(session: Session, post_id: uuid.UUID, original_id: uuid.UUID) -> None:
    """Point a post at the original it duplicates."""
    row = session.get(PostRow, post_id)
    if row is not None:
        row.duplicate_of = original_id


# ---------------------------------------------------------------- firms


def upsert_firm(session: Session, firm: RegisteredFirm) -> None:
    """Insert or replace a registered firm and its aliases."""
    row = session.get(FirmRow, firm.id)
    if row is None:
        row = FirmRow(id=firm.id)
        session.add(row)
    row.name = firm.name
    row.kind = firm.kind
    row.country = firm.country
    row.services = list(firm.services)
    row.register_url = firm.register_url
    row.active = True
    row.synced_at = utcnow()
    session.flush()
    for alias in session.scalars(select(FirmAliasRow).where(FirmAliasRow.firm_id == firm.id)):
        session.delete(alias)
    session.flush()
    wanted = (
        [(a, "trade_name") for a in firm.aliases]
        + [(d, "domain") for d in firm.domains]
        + [(h, "handle") for h in firm.handles]
    )
    for name, alias_type in dict.fromkeys(wanted):
        session.add(FirmAliasRow(firm_id=firm.id, alias=name, alias_type=alias_type))
    session.flush()


def _firms_by_id(session: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, RegisteredFirm]:
    if not ids:
        return {}
    rows = session.scalars(select(FirmRow).where(FirmRow.id.in_(ids))).all()
    aliases: dict[uuid.UUID, list[FirmAliasRow]] = defaultdict(list)
    for alias in session.scalars(
        select(FirmAliasRow).where(FirmAliasRow.firm_id.in_(ids)).order_by(FirmAliasRow.id)
    ):
        aliases[alias.firm_id].append(alias)
    return {
        row.id: RegisteredFirm(
            id=row.id,
            name=row.name,
            aliases=[a.alias for a in aliases[row.id] if a.alias_type in _ALIAS_TYPES_AS_ALIAS],
            domains=[a.alias for a in aliases[row.id] if a.alias_type == "domain"],
            handles=[a.alias for a in aliases[row.id] if a.alias_type == "handle"],
            kind=row.kind,
            country=row.country,
            services=list(row.services or []),
            register_url=row.register_url,
            fictional=row.source != "knf",
        )
        for row in rows
    }


def firm_sources(session: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Where each firm comes from: `knf` (the register) or `fixture` / `demo` (fictional)."""
    if not ids:
        return {}
    rows = session.execute(select(FirmRow.id, FirmRow.source).where(FirmRow.id.in_(ids))).all()
    return {firm_id: source for firm_id, source in rows}


def list_firms(session: Session) -> list[RegisteredFirm]:
    """Return all active registered firms."""
    ids = set(session.scalars(select(FirmRow.id).where(FirmRow.active.is_(True))))
    return sorted(_firms_by_id(session, ids).values(), key=lambda f: f.name)


def sync_firms(
    session: Session,
    firms: list[RegisteredFirm],
    source: str,
    details: dict[uuid.UUID, dict[str, Any]] | None = None,
    *,
    deactivate_missing: bool = True,
) -> tuple[int, int]:
    """Bulk upsert firms of one `source`; deactivate that source's firms not in `firms`.

    Returns (added, removed).
    """
    details = details or {}
    existing = {
        row.id: row for row in session.scalars(select(FirmRow).where(FirmRow.source == source))
    }
    wanted = {firm.id: firm for firm in firms}
    ids = list(wanted)
    for chunk in range(0, len(ids), 500):
        session.execute(
            delete(FirmAliasRow).where(FirmAliasRow.firm_id.in_(ids[chunk : chunk + 500]))
        )
    now = utcnow()
    added = 0
    for firm in wanted.values():
        row = existing.get(firm.id) or session.get(FirmRow, firm.id)
        if row is None:
            row = FirmRow(id=firm.id)
            session.add(row)
            added += 1
        elif not row.active:
            added += 1
        row.name = firm.name
        row.kind = firm.kind
        row.country = firm.country
        row.services = list(firm.services)
        row.register_url = firm.register_url
        row.active = True
        row.synced_at = now
        row.source = source
        row.details = details.get(firm.id)
        supervisor = (row.details or {}).get("supervisor")
        row.supervisor = str(supervisor)[:100] if supervisor else None
    session.flush()
    for firm in wanted.values():
        typed = (
            [(a, "trade_name") for a in firm.aliases]
            + [(d, "domain") for d in firm.domains]
            + [(h, "handle") for h in firm.handles]
        )
        session.add_all(
            FirmAliasRow(firm_id=firm.id, alias=name[:300], alias_type=kind)
            for name, kind in dict.fromkeys(typed)
        )
    removed = 0
    if deactivate_missing:
        for firm_id, row in existing.items():
            if firm_id not in wanted and row.active:
                row.active = False
                removed += 1
    session.flush()
    return added, removed


def _findings_per_firm(session: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    rows = session.execute(
        select(FindingRow.firm_id, func.count())
        .where(FindingRow.firm_id.in_(ids))
        .group_by(FindingRow.firm_id)
    ).all()
    return {firm_id: count for firm_id, count in rows if firm_id is not None}


def search_firms(
    session: Session,
    query: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[FirmSummary]]:
    """Active firms whose name, alias or domain contains `query` (case/diacritics-insensitive)."""
    from investwatch.registry.normalize import fold

    stmt = select(FirmRow.id, FirmRow.name, FirmRow.kind).where(FirmRow.active.is_(True))
    if kind:
        stmt = stmt.where(FirmRow.kind == kind)
    rows_found = session.execute(stmt).all()
    names: dict[uuid.UUID, str] = {i: n for i, n, _ in rows_found}
    # Polish firms first on ties ("XTB S.A." before the Cypriot "XTB Ltd").
    domestic = {i for i, _, k in rows_found if k in ("dom_maklerski", "bank_maklerski")}
    needle = fold(query or "").strip()
    if needle:
        aliases: dict[uuid.UUID, list[str]] = defaultdict(list)
        for firm_id, alias in session.execute(select(FirmAliasRow.firm_id, FirmAliasRow.alias)):
            if firm_id in names:
                aliases[firm_id].append(alias)

        def rank(firm_id: uuid.UUID) -> int | None:
            name = fold(names[firm_id])
            if name.startswith(needle):
                return 0
            if needle in name:
                return 1
            if any(needle in fold(a) for a in aliases[firm_id]):
                return 2
            return None

        ranked = [(r, names[i], i) for i in names if (r := rank(i)) is not None]
    else:
        ranked = [(0, name, i) for i, name in names.items()]
    ranked.sort(key=lambda t: (t[0], t[2] not in domestic, fold(t[1])))
    page = [i for _, _, i in ranked[offset : offset + limit]]
    firms = _firms_by_id(session, set(page))
    counts = _findings_per_firm(session, page)
    rows = {r.id: r for r in session.scalars(select(FirmRow).where(FirmRow.id.in_(page)))}
    items = [
        FirmSummary(
            firm=firms[i],
            source=rows[i].source,
            active=rows[i].active,
            findings=counts.get(i, 0),
        )
        for i in page
    ]
    return len(ranked), items


def get_firm_detail(session: Session, firm_id: uuid.UUID) -> FirmDetail | None:
    """One firm with its register facts and number of findings."""
    row = session.get(FirmRow, firm_id)
    if row is None:
        return None
    firm = _firms_by_id(session, {firm_id})[firm_id]
    details = row.details or {}
    return FirmDetail(
        firm=firm,
        source=row.source,
        active=row.active,
        findings=_findings_per_firm(session, [firm_id]).get(firm_id, 0),
        supervisor=row.supervisor,
        legal_form=details.get("legal_form"),
        former_names=list(details.get("former_names") or []),
        trade_names=list(details.get("trade_names") or []),
        former_domains=list(details.get("former_domains") or []),
        address=details.get("address"),
        authorized_at=details.get("authorized_at"),
        notes=details.get("notes"),
        synced_at=row.synced_at.isoformat(),
    )


def log_registry_sync(session: Session, result: SyncResult, renamed: int = 0) -> None:
    """Append one row to `registry_sync_log`."""
    session.add(
        RegistrySyncLogRow(
            added=result.added,
            removed=result.removed,
            renamed=renamed,
            source=result.source,
            fetched_at=result.fetched_at,
            total=result.total,
            per_kind=result.per_kind,
            error=result.error,
        )
    )
    session.flush()


def registry_status(session: Session, history: int = 10) -> RegistryStatus:
    """Last syncs and active firm counts for the "Rejestr" page."""
    logs = session.scalars(
        select(RegistrySyncLogRow).order_by(RegistrySyncLogRow.id.desc()).limit(history)
    ).all()
    results = [
        SyncResult(
            source=log.source or "snapshot",
            fetched_at=log.fetched_at or "",
            per_kind=dict(log.per_kind or {}),
            total=log.total or 0,
            added=log.added,
            removed=log.removed,
            extra_firms=0,
            error=log.error,
        )
        for log in logs
    ]
    counts = session.execute(
        select(FirmRow.source, FirmRow.kind, func.count())
        .where(FirmRow.active.is_(True))
        .group_by(FirmRow.source, FirmRow.kind)
    ).all()
    per_kind: dict[str, int] = defaultdict(int)
    fictional = 0
    for source, kind, count in counts:
        if source == "knf":
            per_kind[kind] += count
        else:
            fictional += count
    return RegistryStatus(
        last_sync=results[0] if results else None,
        synced_at=logs[0].synced_at.isoformat() if logs else None,
        active_per_kind=dict(per_kind),
        total_active=sum(per_kind.values()),
        fictional=fictional,
        history=results,
        attribution=knf_attribution(results[0].fetched_at if results else None),
    )


# ---------------------------------------------------------------- findings


def save_findings(session: Session, findings: list[Finding]) -> list[Finding]:
    """Store findings, replacing the previous result of the same `(post, module)`.

    An analyst decision (status other than `new`) survives re-analysis.
    """
    saved: list[Finding] = []
    for finding in findings:
        if finding.firm is not None:
            upsert_firm(session, finding.firm)
        row = session.scalar(
            select(FindingRow).where(
                FindingRow.post_id == finding.post_id, FindingRow.module == finding.module
            )
        )
        if row is None:
            row = FindingRow(id=finding.id, post_id=finding.post_id, module=finding.module)
            row.status = finding.status
            row.created_at = finding.created_at
            session.add(row)
        row.score = finding.score
        row.risk_level = finding.risk_level
        row.explanation = finding.explanation
        row.quotes = list(finding.quotes)
        row.firm_id = finding.firm.id if finding.firm else None
        row.firm_match = finding.firm_match.model_dump(mode="json") if finding.firm_match else None
        row.advertiser = finding.advertiser
        row.rules = [r.model_dump(mode="json") for r in finding.rules]
        row.model = finding.model
        row.used_llm = finding.used_llm
        row.llm_review = finding.llm_review
        session.flush()
        saved.append(finding.model_copy(update={"id": row.id, "status": row.status}))
    return saved


def set_knf_warning(session: Session, post_id: uuid.UUID, warning: KnfWarning | None) -> None:
    """Flag (or clear) every finding of a post: its publisher is on the KNF warning list."""
    value = warning.model_dump(mode="json") if warning else None
    for row in session.scalars(select(FindingRow).where(FindingRow.post_id == post_id)):
        row.knf_warning = value


def _occurrence(row: PostRow) -> Occurrence:
    return Occurrence(
        post_id=row.id,
        url=row.url,
        platform=row.platform,
        author=row.author,
        first_seen_at=_aware_req(row.first_seen_at),
        last_seen_at=_aware_req(row.last_seen_at),
    )


def _duplicates(session: Session, post_ids: set[uuid.UUID]) -> dict[uuid.UUID, list[PostRow]]:
    """Duplicate posts per original, earliest sighting first."""
    if not post_ids:
        return {}
    out: dict[uuid.UUID, list[PostRow]] = defaultdict(list)
    for row in session.scalars(
        select(PostRow)
        .where(PostRow.duplicate_of.in_(post_ids))
        .order_by(PostRow.first_seen_at, PostRow.id)
    ):
        if row.duplicate_of is not None:
            out[row.duplicate_of].append(row)
    return out


def _views(session: Session, rows: list[tuple[FindingRow, PostRow]]) -> list[FindingView]:
    firms = _firms_by_id(session, {f.firm_id for f, _ in rows if f.firm_id})
    dups = _duplicates(session, {p.id for _, p in rows})
    views = []
    for f, p in rows:
        group = [_occurrence(p), *(_occurrence(d) for d in dups.get(p.id, []))]
        views.append(_view(f, p, firms, group))
    return views


def _view(
    f: FindingRow,
    p: PostRow,
    firms: dict[uuid.UUID, RegisteredFirm],
    group: list[Occurrence],
) -> FindingView:
    return FindingView(
        id=f.id,
        post_id=f.post_id,
        module=f.module,
        score=f.score,
        risk_level=f.risk_level,
        explanation=f.explanation,
        quotes=list(f.quotes or []),
        firm=firms.get(f.firm_id) if f.firm_id else None,
        firm_match=FirmMatch.model_validate(f.firm_match) if f.firm_match else None,
        advertiser=f.advertiser,
        rules=[RuleResult.model_validate(r) for r in f.rules or []],
        model=f.model,
        used_llm=f.used_llm,
        llm_review=f.llm_review,
        duplicates=len(group) - 1,
        status=f.status,
        created_at=_aware_req(f.created_at),
        post=post_from_row(p),
        trace=ProcessingTrace.model_validate(p.trace) if p.trace else None,
        knf_warning=KnfWarning.model_validate(f.knf_warning) if f.knf_warning else None,
        occurrences=group,
        first_seen_at=min(o.first_seen_at for o in group),
        last_seen_at=max(o.last_seen_at for o in group),
    )


def _filtered(filters: FindingFilters) -> Select[FindingRow, PostRow]:
    stmt = select(FindingRow, PostRow).join(PostRow, PostRow.id == FindingRow.post_id)
    if filters.module:
        stmt = stmt.where(FindingRow.module == filters.module)
    if filters.platform:
        stmt = stmt.where(PostRow.platform.in_(filters.platform))
    if filters.collector:
        stmt = stmt.where(PostRow.collector == filters.collector)
    if filters.risk_level:
        stmt = stmt.where(FindingRow.risk_level.in_(filters.risk_level))
    if filters.status:
        stmt = stmt.where(FindingRow.status.in_(filters.status))
    if filters.date_from:
        stmt = stmt.where(FindingRow.created_at >= filters.date_from)
    if filters.date_to:
        stmt = stmt.where(FindingRow.created_at <= filters.date_to)
    if filters.min_score is not None:
        stmt = stmt.where(FindingRow.score >= filters.min_score)
    if filters.q:
        pattern = f"%{filters.q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(PostRow.text).like(pattern),
                func.lower(PostRow.author).like(pattern),
                func.lower(FindingRow.explanation).like(pattern),
                func.lower(FindingRow.advertiser).like(pattern),
            )
        )
    return stmt


def _ordered(filters: FindingFilters) -> Select[FindingRow, PostRow]:
    order = FindingRow.score if filters.sort == "score" else FindingRow.created_at
    return _filtered(filters).order_by(order.desc(), FindingRow.id)


def list_findings(session: Session, filters: FindingFilters) -> FindingsPage:
    """Return one filtered, sorted page of findings with their posts."""
    stmt = _filtered(filters)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page = session.execute(
        _ordered(filters).limit(filters.page_size).offset((filters.page - 1) * filters.page_size)
    ).all()
    items = _views(session, [(f, p) for f, p in page])
    return FindingsPage(items=items, total=total, page=filters.page, page_size=filters.page_size)


def all_findings(session: Session, filters: FindingFilters, limit: int) -> list[FindingView]:
    """Return up to `limit` filtered, sorted findings (paging fields are ignored)."""
    rows = session.execute(_ordered(filters).limit(limit)).all()
    return _views(session, [(f, p) for f, p in rows])


def get_finding(session: Session, finding_id: uuid.UUID) -> FindingView | None:
    """Return one finding with its post."""
    row = session.execute(
        select(FindingRow, PostRow)
        .join(PostRow, PostRow.id == FindingRow.post_id)
        .where(FindingRow.id == finding_id)
    ).first()
    if row is None:
        return None
    return _views(session, [(row[0], row[1])])[0]


def update_finding_status(
    session: Session, finding_id: uuid.UUID, status: Status
) -> FindingView | None:
    """Set the analyst status of a finding."""
    row = session.get(FindingRow, finding_id)
    if row is None:
        return None
    row.status = status
    row.updated_at = utcnow()
    set_analyst_label(session, row)
    session.flush()
    return get_finding(session, finding_id)


# ---------------------------------------------------------------- labels

ANALYST_LABELS: dict[str, int] = {"confirmed": 1, "dismissed": 0}
"""Analyst decision -> label (1 = violation). Other statuses carry no label."""
LabelSource = Literal["all", "golden", "analyst"]


def set_analyst_label(session: Session, finding: FindingRow) -> None:
    """Mirror a finding's status into `labels` (`source=analyst`, one row per finding)."""
    ref = f"finding:{finding.id}"
    row = session.scalar(select(LabelRow).where(LabelRow.source == "analyst", LabelRow.ref == ref))
    label = ANALYST_LABELS.get(finding.status)
    if label is None:
        if row is not None:
            session.delete(row)
        return
    if row is None:
        row = LabelRow(source="analyst", ref=ref, rule_labels={})
        session.add(row)
    row.post_id = finding.post_id
    row.module = finding.module
    row.label = label
    row.updated_at = utcnow()


def replace_golden_labels(session: Session, labels: list[dict[str, Any]]) -> int:
    """Make the `golden` labels exactly `labels` (upsert by `ref`, delete the rest)."""
    existing = {
        r.ref or "": r for r in session.scalars(select(LabelRow).where(LabelRow.source == "golden"))
    }
    keep: set[str] = set()
    for fields in labels:
        ref = str(fields["ref"])
        keep.add(ref)
        row = existing.get(ref)
        if row is None:
            row = LabelRow(source="golden", ref=ref)
            session.add(row)
        for key, value in fields.items():
            setattr(row, key, value)
        row.updated_at = utcnow()
    for ref, row in existing.items():
        if ref not in keep:
            session.delete(row)
    session.flush()
    return len(keep)


def calibration_inputs(
    session: Session, module: ModuleId, source: LabelSource = "all"
) -> tuple[list[tuple[float, int]], list[float], dict[str, int]]:
    """Labelled (score, label) pairs, unlabelled finding scores and label counts per source.

    Golden labels carry their own score; analyst labels take the finding's current score.
    """
    labelled: list[tuple[float, int]] = []
    counts: dict[str, int] = {}
    if source in ("all", "golden"):
        golden = session.execute(
            select(LabelRow.score, LabelRow.label).where(
                LabelRow.source == "golden",
                LabelRow.module == module,
                LabelRow.score.is_not(None),
            )
        ).all()
        labelled += [(float(score or 0.0), int(label)) for score, label in golden]
        counts["golden"] = len(golden)
    analyst_ids: set[uuid.UUID] = set()
    if source in ("all", "analyst"):
        analyst = session.execute(
            select(FindingRow.id, FindingRow.score, LabelRow.label)
            .join(
                FindingRow,
                (FindingRow.post_id == LabelRow.post_id) & (FindingRow.module == LabelRow.module),
            )
            .where(LabelRow.source == "analyst", LabelRow.module == module)
        ).all()
        labelled += [(float(score), int(label)) for _, score, label in analyst]
        analyst_ids = {fid for fid, _, _ in analyst}
        counts["analyst"] = len(analyst)
    unlabelled = [
        float(score)
        for fid, score in session.execute(
            select(FindingRow.id, FindingRow.score).where(FindingRow.module == module)
        )
        if fid not in analyst_ids
    ]
    return labelled, unlabelled, counts


# ---------------------------------------------------------------- settings


def get_thresholds(session: Session) -> Thresholds:
    """Return per-module alert thresholds (model defaults for modules never set)."""
    row = session.get(SettingRow, THRESHOLDS_KEY)
    if row is None or not isinstance(row.value, dict):
        return Thresholds()
    return Thresholds.model_validate(row.value)


def set_thresholds(session: Session, thresholds: Thresholds) -> Thresholds:
    """Persist per-module alert thresholds."""
    row = session.get(SettingRow, THRESHOLDS_KEY)
    if row is None:
        row = SettingRow(key=THRESHOLDS_KEY)
        session.add(row)
    row.value = thresholds.model_dump()
    session.flush()
    return thresholds


# ---------------------------------------------------------------- stats


def _bucket_start(day: date, bucket: TrendBucket) -> date:
    return day - timedelta(days=day.weekday()) if bucket == "week" else day


def trend(
    session: Session,
    bucket: TrendBucket,
    start: date,
    end: date,
    module: ModuleId | None = None,
) -> TrendSeries:
    """Count findings per bucket, module and risk level between `start` and `end` inclusive."""
    since = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    until = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    stmt = select(FindingRow.created_at, FindingRow.module, FindingRow.risk_level).where(
        FindingRow.created_at >= since, FindingRow.created_at < until
    )
    if module:
        stmt = stmt.where(FindingRow.module == module)
    counts: dict[tuple[date, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for created_at, mod, risk in session.execute(stmt):
        key = (_bucket_start(_aware_req(created_at).date(), bucket), mod)
        counts[key][risk] += 1
    modules = [module] if module else list(MODULES)
    points: list[TrendPoint] = []
    day = _bucket_start(start, bucket)
    step = timedelta(days=7 if bucket == "week" else 1)
    while day <= end:
        for mod in modules:
            c = counts.get((day, mod), {})
            points.append(
                TrendPoint(
                    bucket_start=day,
                    module=mod,
                    total=sum(c.values()),
                    high=c.get("high", 0),
                    medium=c.get("medium", 0),
                    low=c.get("low", 0),
                )
            )
        day += step
    return TrendSeries(bucket=bucket, start=start, end=end, points=points)


HOURLY_SPANS = (24, 48)
"""Hourly trend windows: all findings within the last 24 h or 48 h."""
TREND_DAYS = 14


def trend_auto(session: Session, now: datetime, module: ModuleId | None = None) -> TrendSeries:
    """Trend with buckets that fit the data (real timestamps, never shifted).

    Hourly (24 or 48 buckets) when every finding of the last 14 days is from the last 48 hours,
    as after a fresh demo or deployment; daily for 14 days otherwise.
    """
    since = now - timedelta(days=TREND_DAYS)
    stmt = select(func.min(FindingRow.created_at)).where(FindingRow.created_at >= since)
    if module:
        stmt = stmt.where(FindingRow.module == module)
    oldest = session.execute(stmt).scalar_one_or_none()
    hour = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    if oldest is not None:
        age = now - _aware_req(oldest)
        for span in HOURLY_SPANS:
            if age < timedelta(hours=span):
                return trend_hourly(session, hour - timedelta(hours=span - 1), span, module)
    end = now.astimezone(UTC).date()
    return trend(session, "day", end - timedelta(days=TREND_DAYS - 1), end, module)


def trend_hourly(
    session: Session, first: datetime, hours: int, module: ModuleId | None = None
) -> TrendSeries:
    """Count findings per hour, module and risk level for `hours` buckets from `first`."""
    until = first + timedelta(hours=hours)
    stmt = select(FindingRow.created_at, FindingRow.module, FindingRow.risk_level).where(
        FindingRow.created_at >= first, FindingRow.created_at < until
    )
    if module:
        stmt = stmt.where(FindingRow.module == module)
    counts: dict[tuple[datetime, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for created_at, mod, risk in session.execute(stmt):
        at = _aware_req(created_at).astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        counts[(at, mod)][risk] += 1
    modules = [module] if module else list(MODULES)
    points: list[TrendPoint] = []
    for i in range(hours):
        at = first + timedelta(hours=i)
        for mod in modules:
            c = counts.get((at, mod), {})
            points.append(
                TrendPoint(
                    bucket_start=at.date(),
                    bucket_at=at,
                    module=mod,
                    total=sum(c.values()),
                    high=c.get("high", 0),
                    medium=c.get("medium", 0),
                    low=c.get("low", 0),
                )
            )
    return TrendSeries(bucket="hour", start=first.date(), end=until.date(), points=points)


def summary(session: Session) -> Summary:
    """Return headline counts for the dashboard."""
    per: dict[str, dict[str, int]] = {m: defaultdict(int) for m in MODULES}
    for mod, risk, status, n in session.execute(
        select(FindingRow.module, FindingRow.risk_level, FindingRow.status, func.count()).group_by(
            FindingRow.module, FindingRow.risk_level, FindingRow.status
        )
    ):
        bucket = per.setdefault(mod, defaultdict(int))
        bucket["total"] += n
        bucket[risk] += n
        bucket[status] += n
    modules = [
        ModuleSummary(
            module=m,
            total=per[m]["total"],
            high=per[m]["high"],
            medium=per[m]["medium"],
            low=per[m]["low"],
            new=per[m]["new"],
        )
        for m in MODULES
    ]
    return Summary(
        posts=session.scalar(select(func.count()).select_from(PostRow)) or 0,
        findings=sum(m.total for m in modules),
        open_findings=sum(per[m]["new"] + per[m]["in_review"] for m in MODULES),
        modules=modules,
        last_finding_at=_aware(session.scalar(select(func.max(FindingRow.created_at)))),
    )


# ---------------------------------------------------------------- sources


_COLLECTOR_PLATFORM: dict[str, Platform] = {
    "sample": "sample",
    "youtube": "youtube",
    "meta_ad_library": "facebook",
    "tiktok": "tiktok",
    "microsoft_ad_library": "bing",
}


def _source(row: SourceRow, last_run: ScrapeRunRow | None = None) -> Source:
    status = last_run.status if last_run else None
    return Source(
        id=row.id,
        name=row.name,
        platform=_COLLECTOR_PLATFORM.get(row.collector, "web"),
        collector=row.collector,
        target=row.target,
        url=row.target,
        module_hint=row.module_hint,
        cron=row.cron,
        schedule=row.cron,
        enabled=row.enabled,
        next_run_at=_aware(row.next_run_at),
        last_status=row.last_status,
        last_run_at=_aware(last_run.started_at) if last_run else None,
        last_run_status="error" if status == "blocked" else status,
        last_run_items=last_run.items_seen if last_run else 0,
        created_at=_aware_req(row.created_at),
    )


def _last_runs(session: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, ScrapeRunRow]:
    latest: dict[uuid.UUID, ScrapeRunRow] = {}
    if not ids:
        return latest
    for run in session.scalars(
        select(ScrapeRunRow)
        .where(ScrapeRunRow.source_id.in_(ids))
        .order_by(ScrapeRunRow.started_at.desc())
    ):
        latest.setdefault(run.source_id, run)
    return latest


def list_sources(session: Session) -> list[Source]:
    """Return all sources."""
    rows = list(session.scalars(select(SourceRow).order_by(SourceRow.created_at)))
    runs = _last_runs(session, [r.id for r in rows])
    return [_source(r, runs.get(r.id)) for r in rows]


def get_source(session: Session, source_id: uuid.UUID) -> Source | None:
    """Return one source."""
    row = session.get(SourceRow, source_id)
    return _source(row, _last_runs(session, [row.id]).get(row.id)) if row else None


def create_source(session: Session, **fields: Any) -> Source:
    """Insert a source."""
    row = SourceRow(**fields)
    session.add(row)
    session.flush()
    return _source(row)


def update_source(session: Session, source_id: uuid.UUID, **fields: Any) -> Source | None:
    """Update selected columns of a source."""
    row = session.get(SourceRow, source_id)
    if row is None:
        return None
    for key, value in fields.items():
        setattr(row, key, value)
    session.flush()
    return get_source(session, source_id)


def due_sources(session: Session, now: datetime) -> list[Source]:
    """Return enabled sources whose `next_run_at` has passed (or was never set)."""
    rows = session.scalars(
        select(SourceRow).where(
            SourceRow.enabled.is_(True),
            or_(SourceRow.next_run_at.is_(None), SourceRow.next_run_at <= now),
        )
    )
    return [_source(r) for r in rows]


def start_run(session: Session, source_id: uuid.UUID) -> uuid.UUID:
    """Open a scrape run record."""
    run = ScrapeRunRow(source_id=source_id, status="running")
    session.add(run)
    session.flush()
    return run.id


def finish_run(
    session: Session,
    run_id: uuid.UUID,
    *,
    status: str,
    items_new: int,
    items_seen: int,
    error: str | None = None,
) -> None:
    """Close a scrape run and copy its status onto the source."""
    run = session.get(ScrapeRunRow, run_id)
    if run is None:
        return
    run.status = status
    run.items_new = items_new
    run.items_seen = items_seen
    run.error = error
    run.finished_at = utcnow()
    source = session.get(SourceRow, run.source_id)
    if source is not None:
        source.last_status = status


def list_runs(session: Session, source_id: uuid.UUID, limit: int = 50) -> list[ScrapeRun]:
    """Return the latest runs of a source."""
    rows = session.scalars(
        select(ScrapeRunRow)
        .where(ScrapeRunRow.source_id == source_id)
        .order_by(ScrapeRunRow.started_at.desc())
        .limit(limit)
    )
    return [
        ScrapeRun(
            id=r.id,
            source_id=r.source_id,
            started_at=_aware_req(r.started_at),
            finished_at=_aware(r.finished_at),
            status=r.status,
            items_new=r.items_new,
            items_seen=r.items_seen,
            error=r.error,
        )
        for r in rows
    ]
