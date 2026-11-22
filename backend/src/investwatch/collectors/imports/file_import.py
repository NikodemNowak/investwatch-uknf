"""File import: material an analyst already holds becomes items, with no network access.

Formats:
- `meta_ads_json`: `ads_archive` records (Ad Library API answer saved to a file, `{"data": [...]}`
  or a list);
- `meta_ads_csv`: either ad rows with `ads_archive` column names, or the Ad Library Report CSV
  (`Page ID`, `Page name`, `Disclaimer`, `Amount spent (...)`, `Number of ads in Library`),
  which gives one advertiser summary per page;
- `tiktok_ccl_json`: Commercial Content API answers (`{"data": {"ads": [...]}}` or a list of
  `{"ad": ..., "advertiser": ...}`), e.g. an export from the TikTok ad library;
- `youtube_api_json`: `videos.list` resources (`{"items": [...]}` or a list), e.g. synthetic
  fixtures or an API answer saved by the analyst (keep it no longer than 30 days);
- `uknf_sample` / `posts_jsonl`: generic records (JSON list, JSONL or CSV) with at least `text`
  and ideally `url`, `platform`, `author`, `published_at`.

The content is only parsed (UTF-8 JSON/CSV), never executed. Every item records
`access_mode=file_import`, the file's SHA-256, who imported it and the stated provenance.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime
from typing import Any, Literal, get_args

from investwatch.collectors.official.meta_ads_api import LIBRARY_URL, ad_items
from investwatch.collectors.official.tiktok_ccl_api import ad_item
from investwatch.collectors.official.youtube_api import video_item
from investwatch.collectors.platform import envelope
from investwatch.collectors.schemas import CollectedItem
from investwatch.core.schemas import Platform

ImportFormat = Literal[
    "meta_ads_json",
    "meta_ads_csv",
    "tiktok_ccl_json",
    "youtube_api_json",
    "uknf_sample",
    "posts_jsonl",
]
IMPORT_FORMATS: tuple[str, ...] = get_args(ImportFormat)
MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_RECORDS = 5000
_PLATFORMS: tuple[str, ...] = get_args(Platform)
_LIST_COLUMNS = (
    "ad_creative_bodies",
    "ad_creative_link_titles",
    "ad_creative_link_descriptions",
    "ad_creative_link_captions",
    "publisher_platforms",
    "bylines",
)


class ImportFileError(ValueError):
    """The file cannot be imported (format, encoding, size); the message is user-facing."""


def _decode(content: bytes) -> str:
    if len(content) > MAX_IMPORT_BYTES:
        raise ImportFileError(f"file larger than {MAX_IMPORT_BYTES // (1024 * 1024)} MB")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportFileError("file is not UTF-8") from exc


def _records(text: str) -> list[dict[str, Any]]:
    """JSON (list or wrapped list), JSONL or CSV -> list of dicts."""
    stripped = text.lstrip()
    if stripped.startswith(("[", "{")):
        try:
            data = json.loads(stripped)
        except ValueError:
            data = None
        if data is not None:
            if isinstance(data, dict):
                inner = data.get("data", data.get("items", data.get("posts", [data])))
                if isinstance(inner, dict):
                    inner = inner.get("ads", [inner])
                data = inner
            if not isinstance(data, list):
                raise ImportFileError("JSON must hold a list of records")
            return [r for r in data if isinstance(r, dict)][:MAX_RECORDS]
        rows = []
        for n, line in enumerate(stripped.splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise ImportFileError(f"line {n} is not valid JSON") from exc
            if isinstance(row, dict):
                rows.append(row)
        return rows[:MAX_RECORDS]
    reader = csv.DictReader(io.StringIO(text))
    return [dict(r) for r in reader][:MAX_RECORDS]


def _split(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, list):
            return [str(v) for v in parsed]
    return [p.strip() for p in text.replace("\n", "|").split("|") if p.strip()]


def _date(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def _report_row(row: dict[str, Any], target: str, prov: dict[str, Any]) -> CollectedItem | None:
    page_id = str(row.get("Page ID") or row.get("Page Id") or "").strip()
    if not page_id:
        return None
    spent = next((v for k, v in row.items() if k and k.lower().startswith("amount spent")), "")
    name = str(row.get("Page name") or row.get("Page Name") or page_id)
    payer = str(row.get("Disclaimer") or "").strip()
    count = str(row.get("Number of ads in Library") or "").strip()
    text = "\n".join(
        part
        for part in (
            f"Reklamodawca: {name}",
            f"Płatnik: {payer}" if payer else "",
            f"Wydatki: {spent}" if spent else "",
            f"Liczba reklam w Bibliotece: {count}" if count else "",
        )
        if part
    )
    url = f"{LIBRARY_URL}?view_all_page_id={page_id}"
    return CollectedItem(
        platform="facebook",
        collector="meta_ad_library",
        external_id=f"report:{page_id}",
        url=url,
        author=name,
        author_url=f"https://www.facebook.com/{page_id}",
        text=text,
        raw=envelope("meta_ad_library", url, target, row, record_type="ad_library_report", **prov),
    )


def _generic(row: dict[str, Any], n: int, target: str, prov: dict[str, Any]) -> CollectedItem:
    text = str(row.get("text") or row.get("content") or row.get("tresc") or "").strip()
    url = str(row.get("url") or row.get("link") or "").strip()
    platform = str(row.get("platform") or "web").lower()
    if platform not in _PLATFORMS:
        platform = "web"
    digest = hashlib.sha256(f"{url}\n{text}".encode()).hexdigest()[:16]
    external_id = str(row.get("external_id") or row.get("id") or f"import:{digest}")
    return CollectedItem(
        platform=platform,
        collector="file_import",
        external_id=external_id[:500],
        url=url or f"import:{digest}",
        author=str(row.get("author") or row.get("autor") or "(import)")[:300],
        author_url=str(row.get("author_url") or "") or None,
        text=text,
        lang=str(row.get("lang") or "") or None,
        published_at=_date(row.get("published_at") or row.get("date")),
        fetch_status="ok" if text else "no_text",
        raw=envelope(
            "file_import",
            url or f"import:{digest}",
            target,
            {k: row[k] for k in row if k != "text"},
            record_index=n,
            synthetic=bool(row.get("synthetic")),
            **prov,
        ),
    )


def import_file(
    fmt: str,
    content: bytes,
    *,
    filename: str = "",
    imported_by: str = "analyst",
    provenance_note: str = "",
    module_hint: str | None = None,
) -> list[CollectedItem]:
    """Parse one uploaded file into items; raises `ImportFileError` with a user-facing message."""
    if fmt not in IMPORT_FORMATS:
        raise ImportFileError(
            f"unknown format {fmt!r}; expected one of {', '.join(IMPORT_FORMATS)}"
        )
    text = _decode(content)
    sha256 = hashlib.sha256(content).hexdigest()
    rows = _records(text)
    target = f"import:{filename or sha256[:12]}"
    prov: dict[str, Any] = {
        "access_mode": "file_import",
        "legal_basis": "import pliku przez analityka",
        "imported_by": imported_by,
        "imported_at": datetime.now().astimezone().isoformat(),
        "sha256": sha256,
        "filename": filename,
        "import_format": fmt,
        "provenance_note": provenance_note,
        "module_hint": module_hint,
    }
    items: list[CollectedItem] = []
    for n, row in enumerate(rows):
        if fmt == "meta_ads_csv" and ("Page ID" in row or "Page Id" in row) and "id" not in row:
            report = _report_row(row, target, prov)
            items += [report] if report else []
        elif fmt in {"meta_ads_json", "meta_ads_csv"}:
            ad = dict(row)
            for column in _LIST_COLUMNS:
                if column in ad:
                    ad[column] = _split(ad[column])
            if not (ad.get("id") or ad.get("ad_archive_id")):
                continue
            items += ad_items(ad, target, synthetic=bool(row.get("synthetic")), **prov)
        elif fmt == "tiktok_ccl_json":
            if not (row.get("ad") or {}).get("id"):
                continue
            items.append(ad_item(row, target, synthetic=bool(row.get("synthetic")), **prov))
        elif fmt == "youtube_api_json":
            if not row.get("id") or not isinstance(row.get("snippet"), dict):
                continue
            items.append(video_item(row, target, synthetic=bool(row.get("synthetic")), **prov))
        else:
            items.append(_generic(row, n, target, prov))
    if not items:
        raise ImportFileError(f"no records of format {fmt} found in the file")
    return items
