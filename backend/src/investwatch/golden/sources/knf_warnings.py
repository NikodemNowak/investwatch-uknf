"""KNF public warning list ("Lista ostrzeżeń publicznych KNF").

Source: https://www.knf.gov.pl/dla_konsumenta/ostrzezenia_publiczne, published by the Polish
Financial Supervision Authority under art. 6b of the Act on financial market supervision: the
entities KNF notified to prosecutors for suspected unauthorised financial activity. Public
sector information (Act of 11 August 2021 on open data and re-use of public sector
information); knf.gov.pl robots.txt allows all agents.

Use: (1) entity signal (names, KRS, domains) for the router; (2) seed domains for the archived
page texts in `wayback.py`; (3) the label of those texts: art. 178 UoIF in connection with
art. 69 ust. 2 pkt 4 (portfolio management) or pkt 5 (investment advice) is the regulator's
own finding of the M3 activity.

Data minimisation: the committed snapshot keeps legal persons and entities with a web domain
only; private individuals named on the list are dropped (we do not need them).

Usage (from `backend/`):
    uv run python -m investwatch.golden.sources.knf_warnings   # one request, writes the snapshot
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from investwatch.golden.sources.http import PoliteClient

log = logging.getLogger(__name__)

URL = "https://www.knf.gov.pl/dla_konsumenta/ostrzezenia_publiczne"
LICENCE = (
    "Public sector information, KNF (art. 6b ustawy o nadzorze nad rynkiem finansowym); "
    "re-use with source and retrieval date (ustawa z 11.08.2021 o otwartych danych)"
)
SNAPSHOT = "knf_warnings.json"

SECTIONS: tuple[tuple[str, str], ...] = (
    ("art. 79 ustawy o obrocie", "investment_firm_agent"),
    ("art. 178 ustawy o obrocie", "investment_services"),
    ("Prawo bankowe", "banking"),
    ("ustawy o ofercie publicznej", "public_offering"),
    ("giełdach towarowych", "commodity_exchange"),
    ("działalności ubezpieczeniowej", "insurance"),
    ("pośrednictwie ubezpieczeniowym", "insurance_intermediation"),
    ("funduszach inwestycyjnych", "investment_funds"),
    ("usługach płatniczych", "payment_services"),
    ("dystrybucji ubezpieczeń", "insurance_distribution"),
    ("kredycie konsumenckim", "consumer_credit"),
    ("kredycie hipotecznym", "mortgage_credit"),
    ("finansowaniu społecznościowym", "crowdfunding"),
)
"""Heading fragment -> section code, first match wins (art. 79 before the plain art. 178)."""

_TLDS = (
    "pl|com|net|org|io|eu|co|uk|info|online|pro|biz|ltd|trade|top|xyz|me|app|cc|ch|de|cz|"
    "global|group|capital|finance|club|site|website|live|world|us|ai|vip|exchange|markets|"
    "fund|tech|cloud|space|store|one|today|investments?|money|plus|asia|sc|vc|ru|lt|ua|cy|"
    "ee|lv|sk|ltd|news|company|agency|solutions|services|network|digital|bz|ws|tv|to|"
    "academy|email|link|click|icu|shop"
)
DOMAIN = re.compile(
    r"(?<![@\w.-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:" + _TLDS + r"))(?![\w-])",
    re.I,
)
ART69 = re.compile(r"art\.\s?69 ust\.\s?2 pkt ((?:\d+(?:,\s*|\s+i\s+|\s+oraz\s+)?)+)")
LEGAL_FORM = re.compile(
    r"\b(sp\.\s?z\s?o\.?\s?o|s\.\s?a\.|spółk|ltd|limited|llc|inc\b|gmbh|corp|plc|s\.r\.o|"
    r"o\.ü|oü|b\.v|a\.s\.|holding|fundacj|stowarzyszen|s\.k\.a|sp\.\s?k)",
    re.I,
)


class WarningEntity(BaseModel):
    """One row of the KNF warning list."""

    model_config = ConfigDict(extra="forbid")

    name: str
    identifier: str
    """KRS / NIP / REGON or KNF's note (e.g. "podmiot nie jest zarejestrowany w Polsce")."""
    section: str
    """Statute the notification is under (see `SECTIONS`)."""
    art69_points: list[int]
    """Investment services of art. 69 ust. 2 UoIF named in the notification (4 = portfolio
    management, 5 = investment advice)."""
    domains: list[str]
    final_judgment: bool
    """KNF mentions a final court judgment."""
    info: str

    @property
    def advisory(self) -> bool:
        """Notified for unlicensed investment advice or portfolio management (M3 activity)."""
        return self.section == "investment_services" and bool({4, 5} & set(self.art69_points))


class WarningSnapshot(BaseModel):
    """The committed snapshot (`data/registry/knf_warnings.json`)."""

    model_config = ConfigDict(extra="forbid")

    source: str = URL
    licence: str = LICENCE
    retrieved_at: str
    total_rows: int
    """Rows on the page, before the private-individual filter."""
    entities: list[WarningEntity]


class _Tables(HTMLParser):
    """Collect (heading before the table, rows of cell texts) for every table."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[tuple[str, list[list[str]]]] = []
        self._heading = ""
        self._text: list[str] = []
        self._cell: list[str] | None = None
        self._row: list[str] | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._depth += 1
            heading = " ".join("".join(self._text).split())
            idx = heading.rfind("Zawiadomienia o podejrzeniu")
            self._heading = heading[idx:] if idx >= 0 else self._heading
            self.tables.append((self._heading, []))
            self._text = []
        elif tag == "tr" and self._depth:
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            self._depth = max(0, self._depth - 1)
        elif tag == "td" and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.tables[-1][1].append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)
        elif not self._depth:
            self._text.append(data)
            if len(self._text) > 400:
                self._text = self._text[-200:]


def section_of(heading: str) -> str:
    """Section code of a table heading."""
    return next((code for frag, code in SECTIONS if frag in heading), "other")


def domains_in(text: str) -> list[str]:
    """Web domains mentioned in a cell (lower-case, `www.` dropped, sorted, unique)."""
    found = {m.lower().removeprefix("www.") for m in DOMAIN.findall(text)}
    return sorted(d for d in found if not re.fullmatch(r"(?:sp|s|o|z)\.[a-z.]+", d))


def art69_points(info: str) -> list[int]:
    """Points of art. 69 ust. 2 UoIF named in the notification text."""
    return sorted({int(p) for m in ART69.findall(info) for p in re.findall(r"\d+", m)})


def is_legal_person(name: str, identifier: str, domains: list[str]) -> bool:
    """Keep companies and web-only operators; drop private individuals (data minimisation)."""
    return bool(domains) or "KRS" in identifier or bool(LEGAL_FORM.search(name))


def parse(html: str) -> tuple[int, list[WarningEntity]]:
    """Parse the warning-list page: (rows on the page, kept entities)."""
    parser = _Tables()
    parser.feed(html)
    parser.close()
    total = 0
    out: list[WarningEntity] = []
    for heading, rows in parser.tables:
        section = section_of(heading)
        for row in rows:
            if len(row) < 6:
                continue
            total += 1
            _, name, ident, _prosecutor, verdicts, info = row[:6]
            domains = domains_in(f"{name} {info}")
            if not is_legal_person(name, ident, domains):
                continue
            out.append(
                WarningEntity(
                    name=name,
                    identifier=ident,
                    section=section,
                    art69_points=art69_points(info),
                    domains=domains,
                    final_judgment="prawomocn" in verdicts.lower(),
                    info=info,
                )
            )
    return total, out


def load_snapshot(path: Path) -> WarningSnapshot:
    """Read the committed snapshot."""
    return WarningSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


def main() -> None:
    """Download the list (one request) and write `data/registry/knf_warnings.json`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=_repo() / "data" / "registry" / SNAPSHOT)
    parser.add_argument("--html", type=Path, help="parse a saved page instead of downloading")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.html:
        html = args.html.read_text(encoding="utf-8")
    else:
        client = PoliteClient()
        resp = client.get(URL)
        resp.raise_for_status()
        html = resp.text
        client.close()
    total, entities = parse(html)
    snap = WarningSnapshot(
        retrieved_at=datetime.now(UTC).strftime("%Y-%m-%d"), total_rows=total, entities=entities
    )
    args.out.write_text(
        json.dumps(snap.model_dump(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    log.info("%d rows, kept %d entities -> %s", total, len(entities), args.out)


def _repo() -> Path:
    return Path(__file__).resolve().parents[5]


if __name__ == "__main__":
    main()
