"""Firm domains from the committed KNF register snapshot (plus curated brand domains)."""

from __future__ import annotations

from investwatch.config import Settings, get_settings
from investwatch.registry.knf import load_snapshot
from investwatch.registry.sync import BRANDS_FILE, apply_brands, snapshot_path


def registry_domains(kind: str | None = None, settings: Settings | None = None) -> list[str]:
    """Registrable domains of active register firms (`kind` = register kind, None/`all` = all).

    The register lists no websites for Polish firms, so `data/registry/brands.json` adds the
    well-known brand domains. `host/path` prefixes are reduced to the host.
    """
    settings = settings or get_settings()
    path = snapshot_path(settings)
    if not path.exists():
        return []
    records = apply_brands(load_snapshot(path).records, settings.registry_dir / BRANDS_FILE)
    wanted = None if kind in (None, "", "all") else kind
    domains = (
        d.split("/")[0].lower()
        for r in records
        if wanted is None or r.kind == wanted
        for d in r.domains
    )
    return list(dict.fromkeys(d for d in domains if d))
