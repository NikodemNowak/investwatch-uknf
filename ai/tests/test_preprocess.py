from __future__ import annotations

from investwatch_ai.preprocess import clean_text, detect_lang, sentences


def test_clean_text_strips_html_scripts_and_entities() -> None:
    raw = (
        "<html><head><style>p{color:red}</style><script>alert(1)</script></head>"
        "<body><p>Zarabiaj&nbsp;do <b>25%</b></p><p>miesięcznie!</p></body></html>"
    )
    assert clean_text(raw) == "Zarabiaj do 25%\nmiesięcznie!"


def test_clean_text_normalises_unicode_and_whitespace() -> None:
    # Decomposed "ł" is not composable, but decomposed "ó" is; zero-width space is dropped.
    raw = "Zysk​   bez\tprowizji\n\n\nZłóty  Róg ﬁnanse"
    assert clean_text(raw) == "Zysk bez prowizji\nZłóty Róg finanse"


def test_clean_text_plain_text_is_untouched() -> None:
    assert clean_text("2 < 3 i 5 > 4") == "2 < 3 i 5 > 4"


def test_detect_lang() -> None:
    assert detect_lang("Inwestowanie wiąże się z ryzykiem utraty części kapitału.") == "pl"
    assert detect_lang(
        "CFDs are complex instruments and come with a high risk of losing money."
    ) == ("en")
    assert detect_lang("123 456 %") is None


def test_sentences_split_keeps_offsets() -> None:
    text = "Pierwsze zdanie. Drugie zdanie! Trzecie?"
    spans = sentences(text)
    assert [text[a:b] for a, b in spans] == ["Pierwsze zdanie.", "Drugie zdanie!", "Trzecie?"]
