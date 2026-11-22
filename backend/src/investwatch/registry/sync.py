"""Register synchronisation: KNF pages (or the committed snapshot) -> `firms` table."""

from __future__ import annotations

import json
import logging
import uuid
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from investwatch.config import Settings, get_settings
from investwatch.core.schemas import RegisteredFirm
from investwatch.db import repo
from investwatch.registry import knf
from investwatch.registry.normalize import fold
from investwatch.registry.schemas import KnfRecord, RegisterSnapshot, SyncResult

log = logging.getLogger(__name__)

SNAPSHOT_FILE = "knf_registry.json"
BRANDS_FILE = "brands.json"


def snapshot_path(settings: Settings | None = None) -> Path:
    """Committed snapshot of the four registers."""
    return (settings or get_settings()).registry_dir / SNAPSHOT_FILE


def apply_brands(records: list[KnfRecord], path: Path) -> list[KnfRecord]:
    """Add curated brand aliases and domains (the register lists none for Polish firms)."""
    if not path.exists():
        return records
    brands = json.loads(path.read_text(encoding="utf-8")).get("brands", [])
    by_name = {fold(b["name"]): b for b in brands}
    out: list[KnfRecord] = []
    for record in records:
        brand = by_name.get(fold(record.name))
        if brand is None:
            out.append(record)
            continue
        out.append(
            record.model_copy(
                update={
                    "trade_names": list(
                        dict.fromkeys([*record.trade_names, *brand.get("aliases", [])])
                    ),
                    "domains": list(dict.fromkeys([*record.domains, *brand.get("domains", [])])),
                }
            )
        )
    return out


def load_extra_firms(paths: list[Path]) -> list[RegisteredFirm]:
    """Fictional firms from fixture files, merged by id (later files add domains/aliases)."""
    merged: dict[uuid.UUID, RegisteredFirm] = {}
    adapter = TypeAdapter(list[RegisteredFirm])
    for path in paths:
        if not path.exists():
            log.warning("extra firms file %s not found", path)
            continue
        data: Any = json.loads(path.read_text(encoding="utf-8"))
        firms = adapter.validate_python(data["firms"] if isinstance(data, dict) else data)
        for firm in firms:
            seen = merged.get(firm.id)
            if seen is not None:
                firm = seen.model_copy(
                    update={
                        attr: list(dict.fromkeys([*getattr(seen, attr), *getattr(firm, attr)]))
                        for attr in ("aliases", "domains", "handles", "services")
                    }
                )
            merged[firm.id] = firm
    return list(merged.values())


def fetch_live(settings: Settings) -> RegisterSnapshot:
    """Download the registers from knf.gov.pl (about 40 requests, 1 per second)."""
    with knf.make_client(settings.registry_user_agent) as client:
        return knf.fetch_register(client, interval_s=settings.registry_request_interval_s)


def sync(
    session: Session,
    *,
    live: bool | None = None,
    settings: Settings | None = None,
    fetch: Callable[[Settings], RegisterSnapshot] = fetch_live,
) -> SyncResult:
    """Refresh the `firms` table from the live register, or from the snapshot when offline."""
    settings = settings or get_settings()
    live = settings.registry_live_sync if live is None else live
    source: Literal["live", "snapshot"] = "snapshot"
    error: str | None = None
    snapshot: RegisterSnapshot | None = None
    if live:
        try:
            snapshot = fetch(settings)
            if not snapshot.records:
                raise ValueError("live register returned no firms")
            source = "live"
            _try_save(snapshot, snapshot_path(settings))
        except Exception as exc:  # network, HTML change: the snapshot keeps the system usable
            log.warning("live KNF sync failed (%s); using the snapshot", exc)
            error = f"{type(exc).__name__}: {exc}"[:500]
            snapshot = None
    if snapshot is None:
        snapshot = knf.load_snapshot(snapshot_path(settings))

    records = apply_brands(snapshot.records, settings.registry_dir / BRANDS_FILE)
    firms = [r.to_firm() for r in records]
    details = {r.firm_id: r.details() for r in records}
    added, removed = repo.sync_firms(session, firms, "knf", details)

    extra = load_extra_firms(settings.registry_extra_paths)
    repo.sync_firms(session, extra, "demo")

    result = SyncResult(
        source=source,
        fetched_at=snapshot.fetched_at,
        per_kind=dict(Counter(r.kind for r in records)),
        total=len(records),
        added=added,
        removed=removed,
        extra_firms=len(extra),
        error=error,
    )
    repo.log_registry_sync(session, result)
    log.info("registry sync: %s", result.model_dump())
    return result


def _try_save(snapshot: RegisterSnapshot, path: Path) -> None:
    """Refresh the snapshot file when the data dir is writable (it is read-only in Compose)."""
    try:
        knf.save_snapshot(snapshot, path)
    except OSError as exc:
        log.info("snapshot not saved (%s)", exc)


def main() -> None:
    """Fetch the registers live and rewrite the committed snapshot (`python -m ...sync`)."""
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    snapshot = fetch_live(settings)
    knf.save_snapshot(snapshot, snapshot_path(settings))
    counts = Counter(r.kind for r in snapshot.records)
    log.info("saved %d firms to %s: %s", len(snapshot.records), snapshot_path(settings), counts)


if __name__ == "__main__":
    main()
