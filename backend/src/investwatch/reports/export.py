"""Turn findings into module report rows and serialise them as CSV."""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from investwatch.core.schemas import ModuleId
from investwatch.db.schemas import FindingView, Occurrence
from investwatch.reports.schemas import M1Row, M2Row, M3Row, ReportRow

Separator = Literal[",", ";"]

ROW_MODELS: dict[ModuleId, type[ReportRow]] = {
    "m1_third_party_ad": M1Row,
    "m2_risk_disclosure": M2Row,
    "m3_shadow_advisory": M3Row,
}

# Column order follows the task statement; id and risk level go last.
COLUMNS: dict[ModuleId, tuple[str, ...]] = {
    "m1_third_party_ad": (
        "firm",
        "advertiser",
        "ad_text",
        "url",
        "platform",
        "first_seen_at",
        "last_seen_at",
        "occurrences",
        "score",
        "status",
        "risk_level",
        "finding_id",
    ),
    "m2_risk_disclosure": (
        "firm",
        "material",
        "url",
        "violated_rules",
        "first_seen_at",
        "last_seen_at",
        "occurrences",
        "score",
        "status",
        "risk_level",
        "finding_id",
    ),
    "m3_shadow_advisory": (
        "entity",
        "offer_text",
        "url",
        "art76_signals",
        "first_seen_at",
        "last_seen_at",
        "occurrences",
        "score",
        "status",
        "risk_level",
        "finding_id",
    ),
}

BOM = "﻿"
EXCEL_CELL_MAX = 32_000
"""Excel caps a cell at 32 767 characters; longer text spills into the next row."""
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _locations(f: FindingView) -> list[Occurrence]:
    if f.occurrences:
        return list(f.occurrences)
    p = f.post
    return [
        Occurrence(
            post_id=p.id,
            url=p.url,
            platform=p.platform,
            author=p.author,
            first_seen_at=p.first_seen_at,
            last_seen_at=p.last_seen_at,
        )
    ]


def _failed_rules(f: FindingView) -> list[str]:
    return [f"{r.rule_id}. {r.name} ({r.legal_basis})" for r in f.rules if r.status == "fail"]


def to_rows(f: FindingView) -> list[ReportRow]:
    """Map one finding to report rows of its module, one per location of its occurrence group."""
    locations = _locations(f)
    rows: list[ReportRow] = []
    for n, loc in enumerate(locations):
        # The analysed post keeps the model's advertiser; duplicates name their own author.
        who = (f.advertiser or loc.author) if n == 0 else loc.author
        base: dict[str, object] = {
            "finding_id": f.id,
            "url": loc.url,
            "platform": loc.platform,
            "score": f.score,
            "risk_level": f.risk_level,
            "status": f.status,
            "first_seen_at": loc.first_seen_at,
            "last_seen_at": loc.last_seen_at,
            "occurrences": len(locations),
        }
        if f.module == "m1_third_party_ad":
            rows.append(
                M1Row(
                    **base,
                    firm=f.firm.name if f.firm else "",
                    advertiser=who,
                    ad_text=f.post.text,
                )
            )
        elif f.module == "m2_risk_disclosure":
            rows.append(
                M2Row(
                    **base,
                    firm=f.firm.name if f.firm else loc.author,
                    material=f.post.text,
                    violated_rules=_failed_rules(f),
                )
            )
        else:
            # M3 rules "76a".."76e" are advice elements; "fail" means the element is present.
            rows.append(
                M3Row(
                    **base,
                    entity=who,
                    offer_text=f.post.text,
                    art76_signals=[f"{r.rule_id}. {r.name}" for r in f.rules if r.status == "fail"],
                )
            )
    return rows


def to_row(f: FindingView) -> ReportRow:
    """The report row of the analysed post itself (first location of the group)."""
    return to_rows(f)[0]


def _cell(value: object, decimal_comma: bool) -> str:
    if isinstance(value, list):
        text = " | ".join(str(v) for v in value)
    elif isinstance(value, datetime):
        text = value.isoformat()
    elif isinstance(value, float):
        text = f"{value:.3f}"
        return text.replace(".", ",") if decimal_comma else text
    else:
        text = str(value)
    # Spreadsheets run cells that start with these as formulas (CSV injection).
    if text.startswith(_FORMULA_PREFIXES):
        text = "'" + text
    return text[:EXCEL_CELL_MAX]


def to_csv(module: ModuleId, rows: Sequence[ReportRow], sep: Separator = ",") -> str:
    """Serialise rows as CSV with a UTF-8 BOM and Polish headers.

    With `sep=";"` (Excel in the Polish locale) numbers use a decimal comma.
    """
    model = ROW_MODELS[module]
    columns = COLUMNS[module]
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=sep, lineterminator="\r\n")
    writer.writerow([model.model_fields[c].title or c for c in columns])
    for row in rows:
        writer.writerow([_cell(getattr(row, c), sep == ";") for c in columns])
    return BOM + buf.getvalue()
