"""Evidence reports as PDF: print-optimised HTML rendered by headless Chromium (Playwright).

Chromium is already in the backend image for the crawler, so no PDF library is added. One
finding gives one A4 page (entity, KNF status, problems with their legal basis, evidence crop,
measurements, URL, provenance with SHA-256, timestamps); a module report is an A4 landscape
table with the same rows as the CSV.
"""

from __future__ import annotations

import base64
import html
import logging
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from investwatch.collectors.policy import access_mode_of, legal_basis_of
from investwatch.core.schemas import BBox, ModuleId, RiskLevel, RuleResult, Status, Viewport
from investwatch.db.schemas import FindingView
from investwatch.provenance.schemas import UnderTheHood
from investwatch.reports.export import COLUMNS, ROW_MODELS
from investwatch.reports.schemas import ReportRow

log = logging.getLogger(__name__)

MODULE_PL: dict[ModuleId, str] = {
    "m1_third_party_ad": "Reklamy osób trzecich (M1)",
    "m2_risk_disclosure": "Informacja o ryzyku (M2)",
    "m3_shadow_advisory": "Doradztwo bez zezwolenia (M3)",
}
RISK_PL: dict[RiskLevel, str] = {"high": "wysokie", "medium": "średnie", "low": "niskie"}
STATUS_PL: dict[Status, str] = {
    "new": "nowe",
    "in_review": "w trakcie",
    "confirmed": "potwierdzone naruszenie",
    "dismissed": "oznaczone jako zgodne",
}
FIRM_KIND_PL = {
    "dom_maklerski": "dom maklerski",
    "bank_maklerski": "bank z działalnością maklerską",
    "oddzial_zagraniczny": "oddział firmy zagranicznej",
    "zagraniczna_bez_oddzialu": "firma zagraniczna bez oddziału",
}
ACCESS_PL = {
    "official_api": "oficjalne API",
    "open_dataset": "otwarty zbiór danych",
    "file_import": "import pliku",
    "analyst": "zgłoszenie analityka",
    "crawler": "crawler InvestWatchBot",
}
VIEWPORT_PL: dict[Viewport, str] = {"desktop": "komputer", "tablet": "tablet", "phone": "telefon"}
VIEWPORT_WIDTH: dict[Viewport, int] = {"desktop": 1440, "tablet": 820, "phone": 390}
"""Layout widths of the renderer (`render.capture.VIEWPORTS`)."""
MAX_PROBLEMS = 5
MAX_MEASUREMENTS = 8
MEASURE_PL = {
    "risk_font_px": "czcionka ostrzeżenia [px]",
    "dominant_font_px": "czcionka dominująca [px]",
    "ratio": "stosunek wielkości",
    "contrast": "kontrast",
    "color": "kolor tekstu",
    "background": "tło",
    "opacity": "krycie",
    "y_ratio": "położenie (część wysokości strony)",
    "in_footer": "w stopce",
    "occluded": "zasłonięte",
    "visible": "widoczne",
    "clipped": "ucięte",
    "in_collapsed": "w zwiniętym elemencie",
    "font_px": "czcionka [px]",
}
SKIP_MEASURES = {"role", "tag_path"}
CELL_MAX = 180
DISCLAIMER = (
    "Ocena automatyczna systemu InvestWatch na podstawie publicznie dostępnego materiału; "
    "wymaga weryfikacji analityka i nie stanowi rozstrzygnięcia."
)


CLASSIFIER_SENTENCE = re.compile(
    r"Klasyfikator \([^)]*\): p = (\d+(?:\.\d+)?)(?:[^.]|\.(?!\s|$))*\."
)
"""The `ai` service's classifier sentence ("Klasyfikator (...): p = 0.99; wkład w logit: ...")."""
CLASSIFIER_PLAIN: dict[ModuleId, str] = {
    "m1_third_party_ad": "reklam z linkiem afiliacyjnym lub kodem polecającym",
    "m2_risk_disclosure": "materiałów bez rzetelnej informacji o ryzyku",
    "m3_shadow_advisory": "ofert doradztwa inwestycyjnego bez zezwolenia",
}
"""What the statistical model compares the material to, per module (same words as the UI)."""


def plain_explanation(explanation: str, module: ModuleId) -> str:
    """The explanation for analysts: the classifier's technical sentence in plain Polish.

    The technical sentence stays in the finding's "Pod maską" trace.
    """

    def plain(m: re.Match[str]) -> str:
        certainty = f"{float(m.group(1)):.2f}".replace(".", ",")
        return (
            f"Wzorzec treści podobny do znanych {CLASSIFIER_PLAIN[module]}"
            f" (model statystyczny, pewność {certainty})."
        )

    def unique(m: re.Match[str]) -> str:
        return f"(sygnały: {', '.join(unique_markers(m.group(1)))})"

    return MARKERS.sub(unique, CLASSIFIER_SENTENCE.sub(plain, explanation))


MARKERS = re.compile(r"\(sygnały: ([^)]*)\)")
MAX_MARKERS = 3


def unique_markers(listed: str) -> list[str]:
    """The `ai` marker list, each marker once (ignoring case and line breaks).

    A ranking page repeats its "Advertisement" label on every row (UI: `uniqueMarkers`).
    """
    unique: dict[str, str] = {}
    for raw in listed.split(", "):
        marker = " ".join(raw.split())
        if marker:
            unique.setdefault(marker.casefold(), marker)
    return list(unique.values())


SIGNAL_TITLE = {
    "model": "Sygnał modelu – do weryfikacji",
    "markers": "Sygnały w treści – do weryfikacji",
}
SIGNAL_NOT_RULE = (
    "Żaden ze sprawdzanych wymogów nie jest naruszony, więc to sygnał, a nie stwierdzone"
    " naruszenie."
)
SIGNAL_CHECK: dict[ModuleId, str] = {
    "m1_third_party_ad": (
        "Sprawdź, czy autor zarabia na polecaniu firmy (link afiliacyjny, kod polecający,"
        " prowizja)."
    ),
    "m2_risk_disclosure": "Sprawdź ręcznie informację o ryzyku w materiale.",
    "m3_shadow_advisory": (
        "Sprawdź, czy autor udziela porad dopasowanych do klienta albo mówi, co kupić lub sprzedać."
    ),
}
"""Same words as the finding page (frontend `pl.finding.signal`)."""


@dataclass(frozen=True)
class ModelSignal:
    """Why a high / medium finding without a failed rule scored high (UI: `modelSignalOf`)."""

    title: str
    text: str
    markers: list[str]


def model_signal(
    explanation: str, module: ModuleId, risk: RiskLevel, rules: Sequence[RuleResult]
) -> ModelSignal | None:
    """The risk comes from the classifier or content markers, not from a failed requirement.

    None when a rule failed or the risk is low (then "bez wykrytych naruszeń" is true).
    """
    if risk == "low" or any(r.status == "fail" for r in rules):
        return None
    p = CLASSIFIER_SENTENCE.search(explanation)
    listed = MARKERS.search(explanation)
    markers = unique_markers(listed.group(1) if listed else "")[:MAX_MARKERS]
    if p is None:
        first = "Wynik ryzyka pochodzi ze znaczników w treści."
    else:
        certainty = f"{float(p.group(1)):.2f}".replace(".", ",")
        first = (
            f"Wzorzec treści podobny do znanych {CLASSIFIER_PLAIN[module]}"
            f" (model statystyczny, pewność {certainty})."
        )
    return ModelSignal(
        title=SIGNAL_TITLE["model" if p else "markers"],
        text=f"{first} {SIGNAL_NOT_RULE} {SIGNAL_CHECK[module]}",
        markers=markers,
    )


def _e(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _when(value: datetime | None) -> str:
    if value is None:
        return "–"
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _score(value: float) -> str:
    """Risk score as the dashboard shows it: rounded down, comma ("0,99" for 0.995)."""
    return f"{math.floor(value * 100 + 1e-9) / 100:.2f}".replace(".", ",")


def _short(text: str, limit: int = CELL_MAX) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _hash(value: str | None) -> str:
    return f"<code>{_e(value)}</code>" if value else "–"


@dataclass(frozen=True)
class EvidenceCrop:
    """A cropped screenshot region around one piece of evidence."""

    rule: RuleResult
    viewport: Viewport
    png: bytes


def evidence_target(finding: FindingView) -> tuple[RuleResult, Viewport, BBox] | None:
    """The failed rule whose evidence is located on a screenshot (desktop first)."""
    shots = finding.post.screenshot_keys
    # Measured evidence (font size, contrast) first: that is what a screenshot proves best.
    for measured in (True, False):
        for preferred in ("desktop", "tablet", "phone"):
            for rule in finding.rules:
                if rule.status != "fail":
                    continue
                for ev in rule.evidence:
                    if (
                        ev.bbox
                        and ev.viewport == preferred
                        and ev.viewport in shots
                        and (bool(ev.measurements) or not measured)
                    ):
                        return rule, ev.viewport, ev.bbox
    return None


def _measurements(
    rules: Sequence[RuleResult], viewport: Viewport | None = None
) -> list[tuple[str, str]]:
    """Measured values of the failed rules in one viewport (default: desktop), deduplicated."""
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for rule in rules:
        if rule.status != "fail":
            continue
        evidence = [e for e in rule.evidence if e.measurements]
        shown_vp = viewport or next(
            (v for v in ("desktop", "tablet", "phone") if any(e.viewport == v for e in evidence)),
            None,
        )
        for ev in evidence:
            if ev.viewport not in (shown_vp, None):
                continue
            for name, value in ev.measurements.items():
                if name in SKIP_MEASURES:
                    continue
                shown = f"{value:g}" if isinstance(value, float) else str(value)
                shown = {"true": "tak", "false": "nie"}.get(shown.lower(), shown)
                label = MEASURE_PL.get(name, name)
                if (label, shown) in seen:
                    continue
                seen.add((label, shown))
                out.append((f"{label} (reg. {rule.rule_id})", shown))
    return out[:MAX_MEASUREMENTS]


FICTIONAL_FIRM = "Firma fikcyjna (demo) – udaje wpis w rejestrze KNF"
"""Same words as the UI (`frontend/src/i18n/pl.ts`)."""


def _knf_status(finding: FindingView) -> str:
    if finding.firm is not None and finding.firm.fictional:
        # A demo firm only pretends to be registered: no "W rejestrze KNF", no register link.
        return f"{FICTIONAL_FIRM}: <strong>{_e(finding.firm.name)}</strong>"
    if finding.firm is not None:
        kind = FIRM_KIND_PL.get(finding.firm.kind, finding.firm.kind)
        return (
            f"W rejestrze KNF: <strong>{_e(finding.firm.name)}</strong> ({_e(kind)}); "
            f'<a href="{_e(finding.firm.register_url)}">rejestr KNF</a>'
        )
    if finding.module == "m3_shadow_advisory":
        return "Publikujący nie występuje w rejestrach KNF jako podmiot z uprawnieniem (A5)."
    return "Nie dopasowano firmy z rejestru KNF."


def _subject(finding: FindingView) -> str:
    if finding.module == "m1_third_party_ad":
        return finding.advertiser or finding.post.author
    if finding.firm is not None:
        return finding.firm.name
    return finding.advertiser or finding.post.author


_STYLE = """
@page { size: A4; margin: 14mm 14mm 16mm; }
* { box-sizing: border-box; }
body { font-family: Inter, "Segoe UI", Arial, sans-serif; color: #09090b; font-size: 9.5pt;
  line-height: 1.4; margin: 0; }
header { display: flex; justify-content: space-between; align-items: baseline;
  border-bottom: 2px solid #1d4ed8; padding-bottom: 6px; margin-bottom: 10px; }
.brand { font-weight: 700; color: #1d4ed8; letter-spacing: .02em; }
.muted { color: #3f3f46; }
h1 { font-size: 15pt; margin: 0 0 2px; line-height: 1.25; }
h2 { break-after: avoid; font-size: 10.5pt; margin: 12px 0 5px; text-transform: uppercase;
  letter-spacing: .04em;
  color: #3f3f46; }
table { border-collapse: collapse; width: 100%; }
.facts td { padding: 2px 6px 2px 0; vertical-align: top; }
.facts td:first-child { color: #3f3f46; width: 30%; white-space: nowrap; }
.pill { display: inline-block; padding: 1px 7px; border-radius: 999px; font-weight: 600;
  font-size: 8.5pt; }
.pill--high { background: #fee2e2; color: #b91c1c; }
.pill--medium { background: #fef3c7; color: #b45309; }
.pill--low { background: #f4f4f5; color: #3f3f46; }
ol.problems { margin: 0; padding-left: 18px; }
ol.problems li { margin-bottom: 4px; }
.law { color: #1d4ed8; font-size: 8.5pt; }
.crop img { display: block; max-width: 100%; max-height: 200px; border: 1px solid #e4e4e7;
  margin-bottom: 4px; }
.measures { columns: 2; column-gap: 18px; }
.crop table td { padding: 1px 6px 1px 0; font-size: 8.5pt; }
code { font-family: "JetBrains Mono", Consolas, monospace; font-size: 7.5pt;
  word-break: break-all; }
a { color: #1d4ed8; word-break: break-all; }
footer { margin-top: 12px; border-top: 1px solid #e4e4e7; padding-top: 6px; font-size: 8pt;
  color: #3f3f46; }
.grid { width: 100%; font-size: 8pt; }
.grid th { text-align: left; background: #f4f4f5; padding: 4px 5px;
  border-bottom: 1px solid #d4d4d8; }
.grid td { padding: 4px 5px; border-bottom: 1px solid #e4e4e7; vertical-align: top; }
.grid tr { page-break-inside: avoid; }
"""


def _doc(title: str, body: str, *, landscape: bool = False) -> str:
    page = "@page { size: A4 landscape; margin: 12mm; }" if landscape else ""
    return (
        '<!doctype html><html lang="pl"><head><meta charset="utf-8">'
        f"<title>{_e(title)}</title><style>{_STYLE}{page}</style></head>"
        f"<body>{body}</body></html>"
    )


def finding_html(
    finding: FindingView,
    hood: UnderTheHood | None,
    crop: EvidenceCrop | None,
    generated_at: datetime,
) -> str:
    """One-page evidence report of a finding (print HTML)."""
    post = finding.post
    failed = [r for r in finding.rules if r.status == "fail"]
    problems = "".join(
        f"<li><strong>{_e(r.name)}</strong> – {_e(_short(r.explanation, 240))}"
        f'<br><span class="law">{_e(r.legal_basis)}</span></li>'
        for r in failed[:MAX_PROBLEMS]
    )
    more = len(failed) - MAX_PROBLEMS
    if more > 0:
        problems += f'<li class="muted">… oraz {more} innych (pełna lista w systemie)</li>'
    signal = model_signal(finding.explanation, finding.module, finding.risk_level, finding.rules)
    if signal is not None:
        found = (
            "<br>Znalezione w treści: " + ", ".join(f"„{_e(m)}”" for m in signal.markers)
            if signal.markers
            else ""
        )
        problems = (
            f"<li><strong>{_e(signal.title)}</strong> – {_e(signal.text)}{found}"
            '<br><span class="law">Ocena modelu, nie wymóg z przepisu</span></li>'
        )
    elif not failed:
        problems = "<li>Nie wykryto naruszonych reguł.</li>"

    fetch = hood.fetch if hood else None
    mode = (fetch.access_mode if fetch else None) or access_mode_of(post.collector)
    basis = (fetch.legal_basis if fetch else None) or legal_basis_of(post.collector)
    source_line = f"{_e(ACCESS_PL.get(mode, mode))} · {_e(basis)}"
    if hood and hood.source:
        source_line += f"<br>źródło monitorowane: {_e(hood.source.name)} ({_e(hood.source.cron)})"
    fetched = fetch.fetched_at if fetch and fetch.fetched_at else post.last_seen_at
    shot = next((o for o in (hood.objects if hood else []) if o.kind == "screenshot"), None)
    if crop is not None:
        shot = next((o for o in (hood.objects if hood else []) if o.label == crop.viewport), shot)
    warning = (
        f"<tr><td>Lista ostrzeżeń KNF</td><td><strong>{_e(finding.knf_warning.name)}</strong>"
        f" (stan listy z {_e(finding.knf_warning.as_of)})</td></tr>"
        if finding.knf_warning
        else ""
    )
    facts = f"""
<table class="facts">
<tr><td>Podmiot</td><td><strong>{_e(_subject(finding))}</strong></td></tr>
<tr><td>Status w KNF</td><td>{_knf_status(finding)}</td></tr>
{warning}
<tr><td>Rodzaj</td><td>{_e(MODULE_PL[finding.module])}</td></tr>
<tr><td>Wynik / ryzyko</td><td>{_score(finding.score)} ·
  <span class="pill pill--{finding.risk_level}">{_e(RISK_PL[finding.risk_level])}</span>
  · status: {_e(STATUS_PL[finding.status])}</td></tr>
<tr><td>Adres materiału</td><td><a href="{_e(post.url)}">{_e(post.url)}</a></td></tr>
<tr><td>Źródło pozyskania</td><td>{source_line}</td></tr>
<tr><td>Pobrano</td><td>{_when(fetched)}</td></tr>
<tr><td>Pierwsze / ostatnie wystąpienie</td>
  <td>{_when(finding.first_seen_at or post.first_seen_at)} /
  {_when(finding.last_seen_at or post.last_seen_at)}
  ({len(finding.occurrences) or 1} lok.)</td></tr>
<tr><td>Wykryto</td><td>{_when(finding.created_at)} ·
  model: <code>{_e(finding.model)}</code></td></tr>
<tr><td>SHA-256 tekstu</td><td>{_hash(post.content_hash)}</td></tr>
<tr><td>SHA-256 zrzutu</td><td>{_hash(shot.sha256 if shot else None)}
  {f"<br><code>{_e(shot.bucket)}/{_e(shot.key)}</code>" if shot else ""}</td></tr>
</table>"""

    evidence = ""
    measures = " · ".join(
        f"{_e(k)}: <strong>{_e(v)}</strong>"
        for k, v in _measurements(failed, crop.viewport if crop else None)
    )
    if crop is not None:
        data = base64.b64encode(crop.png).decode()
        evidence = f"""
<h2>Dowód na zrzucie ekranu</h2>
<div class="crop">
  <img alt="Wycinek zrzutu" src="data:image/png;base64,{data}">
  <div><strong>{_e(crop.rule.name)}</strong> · widok: {_e(VIEWPORT_PL[crop.viewport])};
  czerwona ramka wskazuje zmierzony element.</div>
  <div class="muted">{measures}</div>
</div>"""
    elif measures:
        evidence = f"<h2>Pomiary</h2><div class='muted'>{measures}</div>"

    quotes = ""
    if finding.quotes and crop is None:  # with a crop the page is full; quotes are in the app
        n = 3
        quoted = "".join(f"<li>„{_e(_short(q, 160))}”</li>" for q in finding.quotes[:n])
        quotes = f"<h2>Cytaty z materiału</h2><ul>{quoted}</ul>"

    body = f"""
<header><span class="brand">InvestWatch · raport dowodowy</span>
<span class="muted">ID {_e(finding.id)}</span></header>
<h1>{_e(_subject(finding))}: {_e(_problems_pl(len(failed), signal is not None))}</h1>
<div class="muted">{_e(MODULE_PL[finding.module])} ·
  {_e(_short(plain_explanation(finding.explanation, finding.module), 640))}</div>
<h2>Dane zgłoszenia</h2>{facts}
<h2>Wykryte problemy i podstawa prawna</h2><ol class="problems">{problems}</ol>
{evidence}{quotes}
<footer>Wygenerowano {_when(generated_at)} · {_e(DISCLAIMER)}</footer>"""
    return _doc(f"Raport dowodowy {finding.id}", body)


def module_html(
    title: str,
    sections: Sequence[tuple[ModuleId, Sequence[ReportRow]]],
    generated_at: datetime,
    *,
    filters: str = "",
    truncated: bool = False,
) -> str:
    """Module report: one table per module, same columns as the CSV (text cut for print)."""
    parts: list[str] = []
    for module, rows in sections:
        model = ROW_MODELS[module]
        columns = [c for c in COLUMNS[module] if c != "finding_id"]
        head = "".join(f"<th>{_e(model.model_fields[c].title or c)}</th>" for c in columns)
        body = "".join(
            "<tr>" + "".join(f"<td>{_cell(getattr(row, c))}</td>" for c in columns) + "</tr>"
            for row in rows
        )
        empty = f"<tr><td colspan='{len(columns)}'>Brak rekordów.</td></tr>"
        parts.append(
            f"<h2>{_e(MODULE_PL[module])} · {_rows_pl(len(rows))}</h2>"
            f"<table class='grid'><thead><tr>{head}</tr></thead>"
            f"<tbody>{body or empty}</tbody></table>"
        )
    note = (
        "<p class='muted'>Lista ucięta do limitu; pełne dane w eksporcie CSV.</p>"
        if truncated
        else ""
    )
    page = f"""
<header><span class="brand">InvestWatch · {_e(title)}</span>
<span class="muted">Wygenerowano {_when(generated_at)}</span></header>
<p class="muted">{_e(filters) or "Bez filtrów"}. {_e(DISCLAIMER)}</p>{note}
{"".join(parts)}"""
    return _doc(title, page, landscape=True)


def _problems_pl(n: int, signal: bool = False) -> str:
    if n == 0:
        return "sygnał do weryfikacji" if signal else "bez wykrytych naruszeń"
    if n == 1:
        return "1 problem"
    few = n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14)
    return f"{n} {'problemy' if few else 'problemów'}"


def _rows_pl(n: int) -> str:
    if n == 1:
        return "1 wiersz"
    few = n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14)
    return f"{n} {'wiersze' if few else 'wierszy'}"


def _cell(value: object) -> str:
    if isinstance(value, list):
        return "<br>".join(_e(_short(str(v), 90)) for v in value) or "–"
    if isinstance(value, datetime):
        return _e(value.astimezone(UTC).strftime("%Y-%m-%d %H:%M"))
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return f'<a href="{_e(value)}">{_e(_short(value, 70))}</a>'
    if value in RISK_PL:
        return _e(RISK_PL[value])
    if value in STATUS_PL:
        return _e(STATUS_PL[value])
    return _e(_short(str(value)))


class PdfRenderer(Protocol):
    """Turns print HTML into PDF bytes and crops screenshots (Chromium; a fake in tests)."""

    def pdf(self, html_doc: str, *, landscape: bool = False, one_page: bool = False) -> bytes:
        """Render `html_doc` to PDF; `one_page` shrinks it to fit a single page."""
        ...

    def crop(self, png: bytes, bbox: BBox, viewport: Viewport) -> bytes:
        """Cut the region around `bbox` (CSS px of the page) out of a full-page screenshot."""
        ...


def get_pdf_renderer() -> PdfRenderer:
    """FastAPI dependency: headless Chromium (`render.pdf`); tests override it."""
    from investwatch.render.pdf import ChromiumPdf

    return ChromiumPdf()
