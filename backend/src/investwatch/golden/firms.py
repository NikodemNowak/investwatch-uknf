"""Fictional firms used by the synthetic part of the golden set.

None of these firms exist; the `.example` domains are reserved (RFC 2606).
"""

from __future__ import annotations

import uuid
from typing import Literal

from investwatch.core.schemas import FirmMatch, RegisteredFirm

GOLDEN_NS = uuid.UUID("2b0c8f5e-3d71-4c1a-9a51-0d6e7c1f9b22")
REGISTER_URL = "https://www.knf.gov.pl/podmioty/wyszukiwarka_podmiotow"
ALL_SERVICES = ["A1", "A2", "A3", "A4", "A5"]

_SPECS: list[tuple[str, str, str, str]] = [
    # (key, official name, trade name, kind)
    ("sowa", "Sowa Maklerska Dom Maklerski S.A.", "Sowa Maklerska", "dom_maklerski"),
    ("nordbrok", "Nordbrok Invest Dom Maklerski S.A.", "Nordbrok", "dom_maklerski"),
    ("baltyk", "Bałtyk Securities Dom Maklerski S.A.", "Bałtyk Securities", "dom_maklerski"),
    ("kopernik", "Kopernik Trade Ltd", "Kopernik Trade", "zagraniczna_bez_oddzialu"),
    ("tatra", "Tatra Fundusze Dom Maklerski S.A.", "Tatra Fundusze", "dom_maklerski"),
    ("wawel", "Wawel Broker Dom Maklerski S.A.", "Wawel Broker", "dom_maklerski"),
    ("mazury", "Mazury Capital Partners Dom Maklerski S.A.", "Mazury Capital", "dom_maklerski"),
    ("odra", "Odra Markets Ltd", "Odra Markets", "zagraniczna_bez_oddzialu"),
    ("pilica", "Pilica Inwestycje Dom Maklerski S.A.", "Pilica Inwestycje", "dom_maklerski"),
]


def _firm(key: str, name: str, trade: str, kind: str) -> RegisteredFirm:
    domain = f"{trade.lower().replace(' ', '').replace('ł', 'l')}.example"
    return RegisteredFirm.model_validate(
        {
            "id": uuid.uuid5(GOLDEN_NS, f"firm:{key}"),
            "name": name,
            "aliases": [trade],
            "domains": [domain],
            "handles": [f"@{key}_official"],
            "kind": kind,
            "country": "CY" if name.endswith("Ltd") else "PL",
            "services": ALL_SERVICES,
            "register_url": REGISTER_URL,
        }
    )


FIRMS: dict[str, RegisteredFirm] = {key: _firm(key, *rest) for key, *rest in _SPECS}
"""Fictional firms keyed by a short id."""


def firm_match(
    key: str, on: Literal["author", "content"], matched_text: str | None = None
) -> FirmMatch:
    """Router input for a synthetic item: domain match as author, alias match in content."""
    firm = FIRMS[key]
    if on == "author":
        return FirmMatch(
            firm=firm, confidence=1.0, method="domain", matched_text=firm.domains[0], on="author"
        )
    return FirmMatch(
        firm=firm,
        confidence=0.9,
        method="alias",
        matched_text=matched_text or firm.aliases[0],
        on="content",
    )
