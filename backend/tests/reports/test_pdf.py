"""Evidence PDF: print HTML content, endpoints (fake renderer) and one real Chromium run."""

from __future__ import annotations

import html
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from investwatch.core.schemas import BBox, Viewport
from investwatch.main import api as app
from investwatch.reports.pdf import get_pdf_renderer


class FakePdf:
    """Records the HTML it was given and returns a PDF-looking blob."""

    def __init__(self) -> None:
        self.docs: list[tuple[str, bool]] = []
        self.crops: list[tuple[BBox, Viewport]] = []

    def pdf(self, html_doc: str, *, landscape: bool = False, one_page: bool = False) -> bytes:
        self.docs.append((html_doc, landscape))
        return b"%PDF-1.7 fake"

    def crop(self, png: bytes, bbox: BBox, viewport: Viewport) -> bytes:
        self.crops.append((bbox, viewport))
        return b"\x89PNG crop"


@pytest.fixture
def fake() -> Iterator[FakePdf]:
    renderer = FakePdf()
    app.dependency_overrides[get_pdf_renderer] = lambda: renderer
    yield renderer
    app.dependency_overrides.pop(get_pdf_renderer, None)


@pytest.fixture
def client(seeded: None) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _with_shot(client: TestClient) -> dict[str, object]:
    items = client.get("/api/findings", params={"page_size": 100}).json()["items"]
    return next(
        f
        for f in items
        if f["post"]["screenshot_keys"]
        and any(r["status"] == "fail" and any(e["bbox"] for e in r["evidence"]) for r in f["rules"])
    )


def test_finding_pdf_has_the_evidence(client: TestClient, fake: FakePdf) -> None:
    finding = _with_shot(client)
    r = client.get(f"/api/findings/{finding['id']}/report.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert "attachment" in r.headers["content-disposition"]
    doc, landscape = fake.docs[0]
    assert not landscape
    post = finding["post"]
    assert isinstance(post, dict)
    assert html.escape(str(post["url"])) in doc and str(post["content_hash"]) in doc
    failed = [r for r in finding["rules"] if r["status"] == "fail"]  # type: ignore[attr-defined]
    assert failed[0]["legal_basis"] in doc
    assert "data:image/png;base64," in doc and fake.crops  # the cropped screenshot
    assert "SHA-256 zrzutu" in doc and "Status w KNF" in doc
    assert "<script" not in doc


def test_finding_pdf_escapes_material_text(client: TestClient, fake: FakePdf) -> None:
    r = client.post("/api/check", json={"text": "<script>alert(1)</script> Gwarantujemy zysk 40%!"})
    job = client.get(f"/api/check/{r.json()['job_id']}").json()
    assert client.get(f"/api/findings/{job['finding_ids'][0]}/report.pdf").status_code == 200
    doc = fake.docs[-1][0]
    assert "<script>alert" not in doc


def test_module_pdf_mirrors_the_csv(client: TestClient, fake: FakePdf) -> None:
    r = client.get("/api/reports/m2.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    doc, landscape = fake.docs[-1]
    assert landscape and "Naruszone reguły (podstawa prawna)" in doc
    csv_rows = client.get("/api/reports/m2.csv").text.strip().splitlines()[1:]
    assert doc.count("<tr><td>") == len(csv_rows)
    r = client.get("/api/reports/all.pdf", params={"risk_level": "high"})
    assert r.status_code == 200
    doc = fake.docs[-1][0]
    assert doc.count("<table class='grid'>") == 3 and "ryzyko = high" in doc
    assert client.get("/api/reports/m9.pdf").status_code == 404


@pytest.mark.browser
def test_real_chromium_renders_the_report(client: TestClient) -> None:
    from investwatch.render.pdf import ChromiumPdf, page_count

    renderer = ChromiumPdf()
    try:
        renderer.pdf("<p>x</p>")
    except Exception as exc:
        pytest.skip(f"Chromium not available: {exc}")
    app.dependency_overrides[get_pdf_renderer] = lambda: renderer
    try:
        finding = _with_shot(client)
        r = client.get(f"/api/findings/{finding['id']}/report.pdf")
    finally:
        app.dependency_overrides.pop(get_pdf_renderer, None)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert page_count(r.content) == 1  # one A4 page per finding


def test_plain_explanation_hides_the_classifier_internals() -> None:
    from investwatch.reports.pdf import plain_explanation

    text = (
        "Elementy doradztwa: a, b. Klasyfikator (embedding bge-m3 + leksykon): p = 0.99; "
        "wkład w logit: rekomendacja +1.2, embedding +0.8. Podmiot figuruje na liście."
    )
    assert plain_explanation(text, "m3_shadow_advisory") == (
        "Elementy doradztwa: a, b. Wzorzec treści podobny do znanych ofert doradztwa"
        " inwestycyjnego bez zezwolenia (model statystyczny, pewność 0,99)."
        " Podmiot figuruje na liście."
    )
    m1 = plain_explanation("X promuje Y. Klasyfikator (leksykon): p = 0.83.", "m1_third_party_ad")
    assert m1 == (
        "X promuje Y. Wzorzec treści podobny do znanych reklam z linkiem afiliacyjnym lub kodem"
        " polecającym (model statystyczny, pewność 0,83)."
    )
    assert plain_explanation("Naruszenia: brak.", "m2_risk_disclosure") == "Naruszenia: brak."


def test_plain_explanation_lists_each_signal_once() -> None:
    """A ranking page repeats "Advertisement": the report names each signal once."""
    from investwatch.reports.pdf import model_signal, plain_explanation

    text = "X promuje Y (sygnały: Advertisement, advertisement, z mojego\nlinku, Advertisement)."
    assert plain_explanation(text, "m1_third_party_ad") == (
        "X promuje Y (sygnały: Advertisement, z mojego linku)."
    )
    signal = model_signal(text, "m1_third_party_ad", "high", [])
    assert signal is not None
    assert signal.markers == ["Advertisement", "z mojego linku"]


def test_finding_pdf_shows_a_fictional_firm_honestly(client: TestClient, fake: FakePdf) -> None:
    items = client.get("/api/findings", params={"page_size": 100}).json()["items"]
    finding = next(f for f in items if f["firm"] and f["firm"]["fictional"])
    assert client.get(f"/api/findings/{finding['id']}/report.pdf").status_code == 200
    doc = fake.docs[-1][0]
    assert "Firma fikcyjna (demo) – udaje wpis w rejestrze KNF" in doc
    assert "W rejestrze KNF" not in doc and "rejestr KNF</a>" not in doc


def test_finding_pdf_explains_a_classifier_signal_without_failed_rules(
    client: TestClient,
) -> None:
    """A ranking page: high risk from the M1 classifier, every checked rule met. The report
    must not say "bez wykrytych naruszeń" / "Nie wykryto naruszonych reguł" next to it."""
    from datetime import UTC, datetime

    from investwatch.db.schemas import FindingView
    from investwatch.reports.pdf import finding_html

    items = client.get("/api/findings", params={"page_size": 100}).json()["items"]
    data = next(f for f in items if f["module"] == "m1_third_party_ad")
    data |= {
        "risk_level": "high",
        "score": 1.0,
        "rules": [r | {"status": "pass"} for r in data["rules"]],
        "explanation": (
            "kontomaniak.pl promuje ALIOR BANK S.A., XTB S.A. i inne firmy (razem 5) (sygnały:"
            " kod promocyjny: KONTOMANIAK, kod promocyjny: KONTOMANIAK, Otwórz rachunek\nKonto);"
            " reklama oznaczona, z ostrzeżeniem o ryzyku. Klasyfikator (leksykon): p = 1.00;"
            " wkład w logit: wezwanie do działania +5.9."
        ),
    }
    doc = finding_html(FindingView.model_validate(data), None, None, datetime.now(UTC))
    assert "bez wykrytych naruszeń" not in doc
    assert "Nie wykryto naruszonych reguł" not in doc
    assert "Sygnał modelu – do weryfikacji" in doc
    assert "Żaden ze sprawdzanych wymogów nie jest naruszony" in doc
    assert "kod promocyjny: KONTOMANIAK" in doc and "Otwórz rachunek Konto" in doc
    assert "logit" not in doc


def test_finding_pdf_low_risk_without_failed_rules_stays_compliant(client: TestClient) -> None:
    from datetime import UTC, datetime

    from investwatch.db.schemas import FindingView
    from investwatch.reports.pdf import finding_html

    items = client.get("/api/findings", params={"page_size": 100}).json()["items"]
    data = next(f for f in items if f["module"] == "m1_third_party_ad")
    data |= {"risk_level": "low", "rules": [r | {"status": "pass"} for r in data["rules"]]}
    doc = finding_html(FindingView.model_validate(data), None, None, datetime.now(UTC))
    assert "bez wykrytych naruszeń" in doc and "Sygnał modelu" not in doc


def test_score_is_rounded_down_like_the_dashboard() -> None:
    from investwatch.reports.pdf import _score

    assert _score(0.995) == "0,99"
    assert _score(0.83) == "0,83"
    assert _score(1.0) == "1,00"
