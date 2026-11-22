from __future__ import annotations

from investwatch.collectors.html_text import html_lang, html_to_text


def test_keeps_header_and_footer_and_skips_scripts() -> None:
    html = """<html lang="pl-PL"><head><title>T</title><style>p{}</style></head><body>
    <header>Materiał marketingowy</header><script>var x = 1;</script>
    <p>Zysk 10%
       rocznie</p><footer><details><summary>Info</summary><p>Ryzyko&nbsp;straty</p></details>
    </footer></body></html>"""
    assert html_to_text(html).splitlines() == [
        "Materiał marketingowy",
        "Zysk 10% rocznie",
        "Info",
        "Ryzyko straty",
    ]
    assert html_lang(html) == "pl"


def test_demo_pages(demo_html: dict[str, str]) -> None:
    hidden = html_to_text(demo_html["hidden-risk.html"])
    assert "38% rocznie" in hidden and "76% rachunków" in hidden
    assert "Materiał marketingowy" in html_to_text(demo_html["ok.html"])
