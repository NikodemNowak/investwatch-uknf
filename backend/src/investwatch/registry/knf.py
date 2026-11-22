"""KNF investment-firm registers: fetch and parse the four pages of attachment 1.

The pages are rendered server-side. Each entity is a key-value `<table>`; struck-through text
(`<strike>`) marks former names, trade names and domains. Lists are paginated with `?page=N`.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import httpx

from investwatch.core.schemas import FirmKind
from investwatch.registry.normalize import (
    PLATFORM_DOMAINS,
    domains_in_text,
    is_distinctive,
    legal_form_of,
    registrable_domain,
    tokens,
)
from investwatch.registry.schemas import KnfRecord, RegisterSnapshot

log = logging.getLogger(__name__)

BASE_URL = (
    "https://www.knf.gov.pl/podmioty/Podmioty_rynku_kapitalowego/"
    "Firmy_inwestycyjne_i_Agenci_firm_inwestycyjnych/"
)
REGISTERS: dict[FirmKind, str] = {
    "dom_maklerski": "domy_maklerskie",
    "bank_maklerski": "Banki_prowadzace_dzialalnosc_maklerska",
    "oddzial_zagraniczny": "notyfikowane_firmy_inwestycyjne_oddzialy",
    "zagraniczna_bez_oddzialu": "notyfikowane_zagraniczne_firmy_inwestycyjne",
}
"""Register kind -> page slug under `BASE_URL` (attachment 1)."""

# "Zakres działalności" of Polish firms uses the KNF numbering of art. 69 UoIF; the KNF table
# (Zakres_dzialalnosci_..._91227.pdf linked from the register) maps it to MiFID II Annex I.
_ART69_TO_MIFID = {
    "1": "A1", "2": "A2", "3": "A3", "4": "A4", "5": "A5", "6": "A7", "7": "A6",
    "8": "A8", "8a": "A8", "8b": "A9", "9": "B1", "10": "B2", "11": "B3", "12": "B3",
    "13": "B4", "14": "B5", "15": "B6", "16": "B7",
}  # fmt: skip

COUNTRIES = {
    "austria": "AT", "belgia": "BE", "bulgaria": "BG", "bułgaria": "BG", "chorwacja": "HR",
    "cypr": "CY", "czechy": "CZ", "dania": "DK", "estonia": "EE", "finlandia": "FI",
    "francja": "FR", "gibraltar": "GI", "grecja": "GR", "hiszpania": "ES", "holandia": "NL",
    "niderlandy": "NL", "irlandia": "IE", "islandia": "IS", "liechtenstein": "LI", "litwa": "LT",
    "luksemburg": "LU", "łotwa": "LV", "malta": "MT", "niemcy": "DE", "norwegia": "NO",
    "polska": "PL", "portugalia": "PT", "rumunia": "RO", "słowacja": "SK", "słowenia": "SI",
    "szwecja": "SE", "węgry": "HU", "włochy": "IT", "wielka brytania": "GB",
}  # fmt: skip
"""Polish country names used by the register -> ISO 3166-1 alpha-2."""

_TRADE_NAME = re.compile(r"nazw[ay]\s+handlow[aey]\s*[:\-–]?\s*", re.IGNORECASE)
_SERVICE_NO = re.compile(r"\b(\d{1,2}[ab]?)\b")
_PARENS = re.compile(r"\([^)]*\)")
_PAREN_ALIAS = re.compile(r"\(([^)]+)\)")

DEFAULT_USER_AGENT = (
    "InvestWatchBot/1.0 (+https://github.com/NikodemNowak/investwatch-uknf; KNF register sync)"
)


# ------------------------------------------------------------------ HTML -> cells


@dataclass
class _Line:
    text: str = ""
    struck: list[bool] = field(default_factory=list)
    hrefs: list[tuple[str, bool]] = field(default_factory=list)

    def add(self, text: str, struck: bool) -> None:
        self.text += text
        self.struck += [struck] * len(text)

    def is_struck(self, start: int = 0, end: int | None = None) -> bool:
        """Majority of the letters in `[start, end)` are struck through."""
        flags = [
            s
            for c, s in zip(self.text[start:end], self.struck[start:end], strict=True)
            if c.isalnum()
        ]
        return bool(flags) and sum(flags) * 2 > len(flags)


Cell = list[_Line]


class _TableParser(HTMLParser):
    """Collect `{th label: cell}` per entity table; a cell is a list of `<br>`-separated lines."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict[str, Cell]] = []
        self._row_label: str | None = None
        self._in_th = False
        self._th_text = ""
        self._cell: Cell | None = None
        self._strike = 0
        self._href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.tables.append({})
        elif tag == "th":
            self._in_th, self._th_text = True, ""
        elif tag == "td":
            self._cell = [_Line()]
        elif tag in ("strike", "s", "del"):
            self._strike += 1
        elif tag in ("br", "li", "p") and self._cell is not None:
            self._cell.append(_Line())
        elif tag == "a" and self._cell is not None:
            self._href = dict(attrs).get("href")
            if self._href:
                self._cell[-1].hrefs.append((self._href, self._strike > 0))
        elif tag == "h4" and self._cell is not None:
            # Hidden validity notes ("[od 10.05.2024]") are not part of the visible value.
            self._strike += 1000

    def handle_endtag(self, tag: str) -> None:
        if tag == "th":
            self._in_th = False
            self._row_label = " ".join(self._th_text.split())
        elif tag == "td" and self._cell is not None:
            if self.tables and self._row_label:
                self.tables[-1][self._row_label] = self._cell
            self._cell, self._row_label = None, None
        elif tag in ("strike", "s", "del"):
            self._strike = max(0, self._strike - 1)
        elif tag == "h4" and self._cell is not None:
            self._strike = max(0, self._strike - 1000)
        elif tag == "a":
            self._href = None

    def handle_data(self, data: str) -> None:
        if self._in_th:
            self._th_text += data
        elif self._cell is not None:
            if self._strike >= 1000:
                return
            self._cell[-1].add(data.replace("\xa0", " "), self._strike > 0)


def _clean(text: str) -> str:
    return " ".join(text.split()).strip(" ,;:")


def _lines(cell: Cell | None, *, struck: bool | None = False) -> list[str]:
    """Non-empty lines; `struck=None` returns all, otherwise only (non-)struck ones."""
    if not cell:
        return []
    return [
        _clean(line.text)
        for line in cell
        if _clean(line.text) and (struck is None or line.is_struck() == struck)
    ]


def _first(table: dict[str, Cell], *labels: str) -> Cell | None:
    for label in labels:
        for key, cell in table.items():
            if key.casefold().startswith(label.casefold()):
                return cell
    return None


# ------------------------------------------------------------------ field parsers


def _services(cell: Cell | None, prefix: str, mapping: dict[str, str] | None = None) -> list[str]:
    codes: list[str] = []
    for text in _lines(cell):
        for number in _SERVICE_NO.findall(_PARENS.sub(" ", text)):
            code = mapping.get(number) if mapping is not None else f"{prefix}{number}"
            if code:
                codes.append(code)
    return list(dict.fromkeys(codes))


def _split_names(line: _Line, start: int) -> list[tuple[str, bool]]:
    """Comma/semicolon-separated names in `line.text[start:]` with their struck flag."""
    out: list[tuple[str, bool]] = []
    pos = start
    for piece in re.split(r"[,;]| / ", line.text[start:]):
        name = _clean(piece).strip("()[] ")
        if name:
            out.append((name, line.is_struck(pos, pos + len(piece))))
        pos += len(piece) + 1  # separators are 1 char except " / " (close enough for flags)
    return out


def _trade_names(cell: Cell | None) -> tuple[list[str], list[str]]:
    current: list[str] = []
    former: list[str] = []
    if not cell:
        return current, former
    collecting = False
    for line in cell:
        text = _clean(line.text)
        match = _TRADE_NAME.search(line.text)
        if match:
            names = _split_names(line, match.end())
            collecting = not names  # "Nazwy handlowe:" followed by one name per line
        elif collecting and text and not domains_in_text(text.lower()):
            names = _split_names(line, 0)
        else:
            collecting = False
            continue
        for name, struck in names:
            if len(name) < 2 or len(name) > 80:
                continue
            (former if struck else current).append(name)
    return list(dict.fromkeys(current)), list(dict.fromkeys(former))


def _domains(cell: Cell | None) -> tuple[list[str], list[str]]:
    current: dict[str, None] = {}
    former: dict[str, None] = {}
    for line in cell or []:
        found: list[tuple[str, bool]] = []
        for href, struck in line.hrefs:
            if href.startswith(("http://", "https://")):
                found.append((registrable_domain(href), struck))
        lowered = line.text.lower()
        for match_domain, matched in domains_in_text(lowered):
            start = lowered.find(matched)
            found.append((match_domain, line.is_struck(start, start + len(matched))))
        for domain, struck in found:
            if not domain or domain in PLATFORM_DOMAINS:
                continue
            (former if struck else current)[domain] = None
    return list(current), [d for d in former if d not in current]


def _country(cell: Cell | None) -> str | None:
    for text in _lines(cell):
        code = COUNTRIES.get(text.casefold())
        if code:
            return code
    return None


# ------------------------------------------------------------------ page parsing


def parse_page(html: str, kind: FirmKind, page_url: str) -> list[KnfRecord]:
    """Parse one register page into records (no network)."""
    parser = _TableParser()
    parser.feed(html)
    records: list[KnfRecord] = []
    for table in parser.tables:
        name_cell = _first(table, "Nazwa")
        current = _lines(name_cell)
        if not current:
            continue
        raw_name = current[0]
        former_names = _lines(name_cell, struck=True)
        trade_names = current[1:]  # banks: "Biuro Maklerskie mBank"
        trade_names += [
            alias
            for alias in (_clean(a) for a in _PAREN_ALIAS.findall(raw_name))
            if alias and is_distinctive(tokens(alias))
        ]
        name = _clean(raw_name)
        extra = _first(table, "Dodatkowe informacje")
        more_names, former_trade = _trade_names(extra)
        domains, former_domains = _domains(extra)
        branch = _lines(_first(table, "Dane teleadresowe oddziału w Polsce - adres"))
        if branch and branch[0].casefold() != name.casefold():
            trade_names.append(branch[0])
        if kind in ("dom_maklerski", "bank_maklerski"):
            services = _services(_first(table, "Zakres działalności"), "", _ART69_TO_MIFID)
            country: str | None = "PL"
            address = ", ".join(
                line for line in _lines(_first(table, "Dane Teleadresowe"))[:2] if line
            )
        else:
            services = _services(
                _first(table, "Usługi inwestycyjne", "A - Usługi inwestycyjne"), "A"
            ) + _services(_first(table, "Usługi dodatkowe", "B - Usługi dodatkowe"), "B")
            country = _country(_first(table, "Państwo macierzyste"))
            address = ", ".join(branch[1:] or _lines(_first(table, "Adres siedziby")))
        dates = _lines(_first(table, "Data zezwolenia", "Data wpływu zawiadomienia"))
        notes = " ".join(_lines(extra))[:300] or None
        records.append(
            KnfRecord(
                kind=kind,
                name=name,
                legal_form=legal_form_of(name),
                former_names=[n for n in former_names if n.casefold() != name.casefold()],
                trade_names=list(
                    dict.fromkeys(
                        t
                        for t in [*trade_names, *more_names]
                        if t and t.casefold() != name.casefold()
                    )
                ),
                former_trade_names=former_trade,
                domains=domains,
                former_domains=former_domains,
                country=country,
                supervisor=" ".join(_lines(_first(table, "Organ nadzoru"))) or None,
                address=address or None,
                services=services,
                authorized_at=dates[0] if dates else None,
                register_url=page_url,
                notes=notes,
            )
        )
    return records


def page_count(html: str, slug: str) -> int:
    """Number of `?page=N` pages linked from the first page (1 when not paginated)."""
    pages = [int(n) for n in re.findall(re.escape(slug) + r"\?page=(\d+)", html)]
    return max([1, *pages])


def merge_records(records: Iterable[KnfRecord]) -> list[KnfRecord]:
    """Merge duplicate entries (same kind and name), keeping the union of their facts."""
    merged: dict[tuple[str, str], KnfRecord] = {}
    for record in records:
        key = (record.kind, record.name.casefold())
        seen = merged.get(key)
        if seen is None:
            merged[key] = record
            continue
        union = {
            attr: list(dict.fromkeys([*getattr(seen, attr), *getattr(record, attr)]))
            for attr in (
                "former_names",
                "trade_names",
                "former_trade_names",
                "domains",
                "former_domains",
                "services",
            )
        }
        merged[key] = seen.model_copy(update=union)
    return list(merged.values())


# ------------------------------------------------------------------ network


def fetch_register(
    client: httpx.Client,
    *,
    interval_s: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    retries: int = 3,
) -> RegisterSnapshot:
    """Download and parse all four registers, one request per `interval_s` (politeness)."""
    records: list[KnfRecord] = []
    urls: list[str] = []
    first = True

    def get(url: str) -> str:
        nonlocal first
        for attempt in range(retries):
            if not first:
                sleep(interval_s * (1 + 2 * attempt))
            first = False
            try:
                response = client.get(url)
                response.raise_for_status()
                return response.text
            except httpx.HTTPError as exc:
                log.warning("KNF fetch %s failed (%s), attempt %d", url, exc, attempt + 1)
                if attempt == retries - 1:
                    raise
        raise AssertionError("unreachable")

    for kind, slug in REGISTERS.items():
        url = BASE_URL + slug
        html = get(url)
        urls.append(url)
        records += parse_page(html, kind, url)
        for page in range(2, page_count(html, slug) + 1):
            page_url = f"{url}?page={page}"
            records += parse_page(get(page_url), kind, page_url)
    return RegisterSnapshot(
        fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        source_urls=urls,
        records=merge_records(records),
    )


def make_client(user_agent: str = DEFAULT_USER_AGENT, timeout_s: float = 60.0) -> httpx.Client:
    """HTTP client with an honest User-Agent for the register pages."""
    return httpx.Client(
        headers={"User-Agent": user_agent, "Accept-Language": "pl"},
        timeout=timeout_s,
        follow_redirects=True,
    )


def load_snapshot(path: Path) -> RegisterSnapshot:
    """Read a saved snapshot (offline fallback and tests)."""
    return RegisterSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


def save_snapshot(snapshot: RegisterSnapshot, path: Path) -> None:
    """Write a snapshot as compact, diff-friendly JSON (one record per line)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    head = snapshot.model_dump_json(exclude={"records"})[:-1]
    records = ",\n".join(r.model_dump_json(exclude_defaults=True) for r in snapshot.records)
    path.write_text(f'{head},"records":[\n{records}\n]}}\n', encoding="utf-8")
