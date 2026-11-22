"""Synthetic part of the golden set: Polish pages and posts with labels known by construction.

M2: marketing pages of fictional firms, each a compliant base page plus a set of defects; every
defect maps to the rules it breaks, so per-rule labels come from the construction, not a judge.
M1: third-party social posts about fictional firms (promotion vs. news, complaints, warnings).
M3: offers of personalised advice by unregistered entities vs. education, licensed firms,
tax or property advice.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Literal

from investwatch.core.schemas import FirmMatch, ModuleId, Platform
from investwatch.golden.firms import FIRMS, firm_match
from investwatch.golden.schemas import GoldenItem, GoldenPost, Provenance, RuleLabel

Topic = Literal["etf", "cfd", "fund", "bonds", "ike"]

DEFECTS = frozenset(
    {
        "tiny_font",
        "low_contrast",
        "occluded",
        "footer_only",
        "collapsed",
        "mobile_clipped",
        "english_risk",
        "no_risk",
        "no_ad_label",
        "no_firm_name",
        "perf_no_disclaimer",
        "perf_dominant",
        "perf_short",
        "forecast_no_disclaimer",
        "tax_no_disclaimer",
        "knf_approval",
        "knf_safety",
    }
)
FEATURES = frozenset({"perf", "forecast", "tax", "knf", "no_gains", "secure_login"})
GENERATOR = Provenance(collector="synthetic", method="generator", compliant="yes")

_HERO: dict[Topic, tuple[str, str]] = {
    "etf": (
        "ETF-y bez prowizji do 100 000 zł obrotu miesięcznie",
        "Zbuduj długoterminowy portfel z funduszy indeksowych. Nasi klienci zyskali na "
        "pasywnym inwestowaniu średnio 7% rocznie.",
    ),
    "cfd": (
        "Handluj CFD na złocie i indeksach z dźwignią do 1:20",
        "Zarabiaj na wzrostach i spadkach. Spready od 0,8 pkt i realizacja zleceń w 30 ms.",
    ),
    "fund": (
        "Fundusz Akcji Wzrostowych: stopa zwrotu 18% w 2025 roku",
        "Portfel spółek wzrostowych z Polski i Europy Środkowej zarządzany aktywnie.",
    ),
    "bonds": (
        "Obligacje korporacyjne z kuponem do 9% w skali roku",
        "Kupuj obligacje notowane na Catalyst bez prowizji przez pierwsze 3 miesiące.",
    ),
    "ike": (
        "IKE z akcjami i ETF-ami: buduj kapitał na emeryturę",
        "Odkładaj w ramach Indywidualnego Konta Emerytalnego. Średni zysk naszych klientów "
        "z portfela ETF wyniósł 6% rocznie.",
    ),
}
_NO_GAINS_HERO = (
    "Godziny pracy i kontakt z Biurem Obsługi Klienta",
    "Zespół obsługi odpowiada na pytania od poniedziałku do piątku w godzinach 8:00–18:00.",
)
_RISK: dict[Topic, str] = {
    "etf": "Inwestowanie w ETF-y wiąże się z ryzykiem utraty części lub całości "
    "zainwestowanego kapitału. Wartość jednostek może zarówno rosnąć, jak i spadać.",
    "cfd": "Kontrakty CFD są złożonymi instrumentami i wiążą się z wysokim ryzykiem szybkiej "
    "utraty środków pieniężnych z powodu dźwigni finansowej. 74% rachunków inwestorów "
    "detalicznych odnotowuje straty w wyniku handlu kontraktami CFD u tego dostawcy.",
    "fund": "Inwestowanie w fundusz wiąże się z ryzykiem utraty części lub całości "
    "zainwestowanego kapitału. Fundusz nie gwarantuje osiągnięcia celu inwestycyjnego.",
    "bonds": "Obligacje korporacyjne wiążą się z ryzykiem niewypłacalności emitenta i "
    "ryzykiem utraty części lub całości zainwestowanego kapitału.",
    "ike": "Inwestowanie w akcje i ETF-y w ramach IKE wiąże się z ryzykiem utraty części "
    "lub całości zainwestowanego kapitału.",
}
_RISK_EN = (
    "Investing involves risk. You may lose part or all of your capital. Past performance "
    "is not a reliable indicator of future results."
)
_BODY = [
    (
        "Jak to działa?",
        "Rachunek otworzysz online w kilka minut. Do weryfikacji tożsamości wystarczy dowód "
        "osobisty i przelew weryfikacyjny z Twojego banku.",
    ),
    (
        "Opłaty",
        "Prowadzenie rachunku jest bezpłatne. Pełna tabela opłat i prowizji jest dostępna w "
        "regulaminie oraz w dokumentach z kluczowymi informacjami (KID).",
    ),
    (
        "Obsługa klienta",
        "Doradcy obsługi klienta odpowiadają na pytania techniczne przez czat w aplikacji i "
        "telefonicznie od poniedziałku do piątku.",
    ),
]
_SECURE_LOGIN = (
    "Bezpieczeństwo konta",
    "Logowanie chroni uwierzytelnianie dwuskładnikowe, a każda dyspozycja przelewu wymaga "
    "potwierdzenia w aplikacji mobilnej. Twoje dane są bezpieczne i szyfrowane.",
)

_CSS = """
body { font-family: Arial, sans-serif; font-size: 16px; color: #1a1a1a; margin: 0;
       background: #ffffff; line-height: 1.5; }
header, main, footer, .hero { max-width: 880px; margin: 0 auto; padding: 16px 24px; }
header { display: flex; justify-content: space-between; align-items: center; }
.logo { font-size: 22px; font-weight: 700; color: #0b3d91; text-decoration: none; }
.label { font-size: 14px; color: #333333; }
.hero h1 { font-size: 36px; margin: 8px 0 12px; }
.risk { font-size: 16px; color: #1a1a1a; background: #fff6d6; border: 1px solid #c9a400;
        padding: 12px; margin: 16px 0; }
.cta { display: inline-block; background: #0b3d91; color: #ffffff; font-size: 18px;
       padding: 12px 24px; text-decoration: none; }
table { border-collapse: collapse; margin: 8px 0; }
td, th { border: 1px solid #999999; padding: 4px 10px; font-size: 16px; }
footer { margin-top: 40px; font-size: 14px; color: #333333; }
footer .legal { font-size: 16px; color: #1a1a1a; background: #ffffff; border: 0; padding: 0; }
"""
_DEFECT_CSS = {
    "tiny_font": ".risk, footer .risk.legal { font-size: 10px; }",
    "low_contrast": ".risk { color: #c8c8c8; background: #ffffff; border: 0; }",
    "occluded": (
        ".risk-wrap { position: relative; } .sticker { position: absolute; inset: 0; "
        "background: #ffca28; color: #000; font-size: 22px; font-weight: 800; display: flex; "
        "align-items: center; justify-content: center; }"
    ),
    "footer_only": "main section { min-height: 420px; }",
    "mobile_clipped": (
        "@media (max-width: 600px) { .risk { white-space: nowrap; overflow: hidden; "
        "text-overflow: ellipsis; } }"
    ),
    "perf_dominant": ".big { font-size: 96px; font-weight: 900; color: #0a7d32; margin: 0; }",
}


@dataclass(frozen=True)
class PageSpec:
    """One synthetic M2 page: a firm, a topic, defects (rule breaches) and extra features."""

    firm: str
    topic: Topic
    flags: frozenset[str] = field(default_factory=frozenset)
    note: str = ""


def _p(text: str, cls: str = "") -> str:
    attr = f' class="{cls}"' if cls else ""
    return f"<p{attr}>{html.escape(text)}</p>"


def _perf_section(flags: frozenset[str]) -> str:
    if "perf_short" in flags:
        rows = [("2025", "+18,0%")]
        period = "Wynik za rok 2025."
    else:
        rows = [
            ("2021", "+12,4%"),
            ("2022", "-9,8%"),
            ("2023", "+15,1%"),
            ("2024", "+6,3%"),
            ("2025", "+18,0%"),
        ]
        period = (
            "Stopy zwrotu w pełnych latach kalendarzowych 2021–2025, w PLN, po potrąceniu "
            "opłaty za zarządzanie. Źródło: obliczenia własne na podstawie wycen jednostek."
        )
    table = "".join(f"<tr><td>{y}</td><td>{r}</td></tr>" for y, r in rows)
    parts = [
        "<section><h2>Wyniki historyczne</h2>",
        f"<table><tr><th>Rok</th><th>Stopa zwrotu</th></tr>{table}</table>",
        _p(period),
        _p(
            "Wyniki podano w PLN; dla inwestorów rozliczających się w innej walucie wynik może "
            "się różnić z powodu wahań kursów walut. Wyniki uwzględniają opłaty i prowizje."
        ),
    ]
    if "perf_no_disclaimer" not in flags:
        parts.append(
            _p(
                "Wyniki historyczne nie są wiarygodnym wskaźnikiem przyszłych wyników i nie "
                "stanowią gwarancji ich osiągnięcia w przyszłości."
            )
        )
    parts.append("</section>")
    return "".join(parts)


def _forecast_section(flags: frozenset[str]) -> str:
    parts = [
        "<section><h2>Prognoza</h2>",
        _p(
            "Prognozujemy, że w scenariuszu bazowym portfel może osiągnąć stopę zwrotu do 9% "
            "rocznie w horyzoncie 5 lat."
        ),
    ]
    if "forecast_no_disclaimer" not in flags:
        parts.append(
            _p(
                "Prognoza opiera się na założeniach dotyczących wzrostu gospodarczego i stóp "
                "procentowych. Prognozy nie są wiarygodnym wskaźnikiem przyszłych wyników."
            )
        )
    parts.append("</section>")
    return "".join(parts)


def _tax_section(flags: frozenset[str]) -> str:
    parts = [
        "<section><h2>Korzyści podatkowe</h2>",
        _p(
            "Zyski wypłacone z IKE po 60. roku życia są zwolnione z 19% podatku od zysków "
            "kapitałowych (podatku Belki)."
        ),
    ]
    if "tax_no_disclaimer" not in flags:
        parts.append(
            _p(
                "Sposób opodatkowania zależy od indywidualnej sytuacji każdego klienta i może "
                "ulec zmianie w przyszłości."
            )
        )
    parts.append("</section>")
    return "".join(parts)


def _knf_text(flags: frozenset[str], firm_name: str) -> str | None:
    if "knf_approval" in flags:
        return "Produkt został zatwierdzony przez Komisję Nadzoru Finansowego."
    if "knf_safety" in flags:
        return (
            "Jesteśmy nadzorowani przez KNF, dlatego Twoje pieniądze są u nas całkowicie "
            "bezpieczne, a zysk jest pewny."
        )
    if "knf" in flags:
        return f"{firm_name} podlega nadzorowi Komisji Nadzoru Finansowego."
    return None


def render_page(spec: PageSpec) -> str:
    """HTML of a synthetic M2 page."""
    firm = FIRMS[spec.firm]
    trade = firm.aliases[0]
    flags = spec.flags
    h1, lead = _NO_GAINS_HERO if "no_gains" in flags else _HERO[spec.topic]
    if "perf_dominant" in flags:
        h1 = f"{trade}: Fundusz Akcji Wzrostowych"
    risk_text = _RISK_EN if "english_risk" in flags else _RISK[spec.topic]
    risk_html = f'<div class="risk" role="note">{html.escape(risk_text)}</div>'
    if "occluded" in flags:
        risk_html = (
            f'<div class="risk-wrap">{risk_html}'
            '<div class="sticker">Tylko dziś: bonus 500 zł na start!</div></div>'
        )
    if "collapsed" in flags:
        risk_html = (
            '<details class="legal"><summary>Informacje o ryzyku</summary>'
            f"{_p(risk_text)}</details>"
        )
    in_hero = not ({"no_risk", "footer_only", "no_gains"} & flags)
    css = _CSS + "".join(_DEFECT_CSS.get(f, "") for f in sorted(flags))

    hero = ['<section class="hero">']
    if "perf_dominant" in flags:
        hero.append(_p("+18% w 2025 roku", "big"))
    hero.append(f"<h1>{html.escape(h1)}</h1>")
    hero.append(_p(lead, "lead"))
    if in_hero:
        hero.append(risk_html)
    hero.append('<a class="cta" href="#">Otwórz rachunek</a></section>')

    sections = list(_BODY)
    if "secure_login" in flags:
        sections.append(_SECURE_LOGIN)
    main = ["<main>"]
    for title, text in sections:
        main.append(f"<section><h2>{html.escape(title)}</h2>{_p(text)}</section>")
    if "perf" in flags or flags & {"perf_no_disclaimer", "perf_dominant", "perf_short"}:
        main.append(_perf_section(flags))
    if "forecast" in flags or "forecast_no_disclaimer" in flags:
        main.append(_forecast_section(flags))
    if "tax" in flags or "tax_no_disclaimer" in flags:
        main.append(_tax_section(flags))
    main.append("</main>")

    footer = ["<footer>"]
    if "footer_only" in flags or "no_gains" in flags:
        footer.append(_p(risk_text, "risk legal"))
    knf = _knf_text(flags, firm.name)
    if knf and "knf" in flags:
        footer.append(_p(knf))
    elif knf:
        main.insert(1, f"<section>{_p(knf)}</section>")
    company = trade if "no_firm_name" in flags else firm.name
    footer.append(
        _p(
            f"{company}, ul. Przykładowa 10, 00-950 Warszawa ({firm.domains[0]}). "
            "Fikcyjna firma na potrzeby testów InvestWatch."
        )
    )
    footer.append("</footer>")

    label = "" if "no_ad_label" in flags else '<p class="label">Materiał marketingowy</p>'
    return (
        '<!doctype html>\n<html lang="pl">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(trade)}: {html.escape(h1)}</title>\n<style>{css}</style>\n"
        "</head>\n<body>\n"
        f'<header><a class="logo" href="#">{html.escape(trade)}</a>{label}</header>\n'
        + "".join(hero)
        + "\n"
        + "".join(main)
        + "\n"
        + "".join(footer)
        + "\n</body>\n</html>\n"
    )


def rule_labels(spec: PageSpec) -> dict[str, RuleLabel]:
    """Per-rule ground truth implied by the construction; ambiguous rules are left out."""
    f = spec.flags
    gains = "no_gains" not in f
    risk = "no_risk" not in f
    hidden = "collapsed" in f
    out: dict[str, RuleLabel] = {
        "1": "fail" if "no_firm_name" in f else "pass",
        "2": "fail" if "no_ad_label" in f else "pass",
        "3": ("fail" if not risk else "pass") if gains else "na",
        "10": ("fail" if "english_risk" in f else "pass") if risk else "na",
    }
    if not risk:
        out |= {"4": "na", "5": "na", "6": "na", "7": "na", "8": "na"}
    else:
        if not hidden:
            out["4"] = "fail" if "tiny_font" in f else "pass"
            out["5"] = "fail" if f & {"low_contrast", "occluded"} else "pass"
            if "occluded" not in f:
                out["8"] = "fail" if f & {"mobile_clipped", "tiny_font"} else "pass"
        if gains:
            out["7"] = "fail" if hidden else "pass"
            if not hidden:
                out["6"] = "fail" if "footer_only" in f else "pass"
        else:
            out["6"] = "na"
            out["7"] = "na"
    perf = "perf" in f or f & {"perf_no_disclaimer", "perf_dominant", "perf_short"}
    if perf:
        out["12a"] = "fail" if "perf_short" in f else "pass"
        out["12b"] = "pass"
        out["13"] = "fail" if "perf_dominant" in f else "pass"
        out["14"] = "fail" if "perf_no_disclaimer" in f else "pass"
    else:
        out |= {"12a": "na", "12b": "na", "13": "na", "14": "na"}
    if "forecast" in f or "forecast_no_disclaimer" in f:
        out["15"] = "fail" if "forecast_no_disclaimer" in f else "pass"
    else:
        out["15"] = "na"
    if "tax" in f or "tax_no_disclaimer" in f:
        out["16"] = "fail" if "tax_no_disclaimer" in f else "pass"
    else:
        out["16"] = "na"
    if "knf_approval" in f:
        out["17"] = "fail"
    elif "knf_safety" in f:
        out["18"] = "fail"
    elif "knf" in f:
        out["17"] = "pass"
        out["18"] = "pass"
    else:
        out["17"] = "na"
        out["18"] = "na"
    return out


def _s(*flags: str) -> frozenset[str]:
    unknown = set(flags) - DEFECTS - FEATURES
    if unknown:
        raise ValueError(f"unknown flags {unknown}")
    return frozenset(flags)


M2_PAGES: list[PageSpec] = [
    PageSpec("sowa", "etf", _s(), "baseline compliant page"),
    PageSpec("sowa", "etf", _s("tiny_font"), "risk warning 10 px"),
    PageSpec("sowa", "cfd", _s("knf_safety"), "KNF supervision as a safety argument"),
    PageSpec("sowa", "fund", _s("perf_no_disclaimer"), "past results without disclaimer"),
    PageSpec("sowa", "ike", _s("tax", "knf"), "tricky: tax note with disclaimer, factual KNF"),
    PageSpec("nordbrok", "cfd", _s("knf"), "compliant CFD page, factual KNF"),
    PageSpec("nordbrok", "etf", _s("footer_only"), "risk only in the footer"),
    PageSpec("nordbrok", "cfd", _s("collapsed"), "risk inside a closed <details>"),
    PageSpec("nordbrok", "fund", _s("forecast_no_disclaimer"), "forecast without disclaimer"),
    PageSpec("nordbrok", "bonds", _s("no_ad_label"), "not labelled as marketing"),
    PageSpec("baltyk", "fund", _s("perf"), "tricky: full 5-year performance, compliant"),
    PageSpec("baltyk", "etf", _s("low_contrast"), "pale grey risk warning"),
    PageSpec("baltyk", "cfd", _s("english_risk"), "risk warning in English"),
    PageSpec("baltyk", "ike", _s("tax_no_disclaimer"), "tax benefit without disclaimer"),
    PageSpec("baltyk", "bonds", _s("no_risk"), "gains claims, no risk warning at all"),
    PageSpec("kopernik", "bonds", _s(), "baseline compliant page"),
    PageSpec("kopernik", "cfd", _s("occluded"), "sticker covers the risk warning"),
    PageSpec("kopernik", "etf", _s("mobile_clipped"), "risk cut on phones"),
    PageSpec("kopernik", "fund", _s("knf_approval"), "suggests KNF approval"),
    PageSpec("kopernik", "fund", _s("perf_dominant"), "past result is the biggest element"),
    PageSpec("tatra", "fund", _s("forecast"), "tricky: forecast with disclaimer"),
    PageSpec("tatra", "fund", _s("perf_short"), "only one year of performance"),
    PageSpec("tatra", "etf", _s("no_firm_name"), "trade name only, no legal name"),
    PageSpec("tatra", "cfd", _s("tiny_font", "footer_only"), "two defects"),
    PageSpec("tatra", "etf", _s("no_gains"), "tricky: info page, risk in footer, no gains"),
    PageSpec("wawel", "ike", _s("tax"), "tricky: IKE tax note with disclaimer"),
    PageSpec("wawel", "etf", _s("knf_safety"), "KNF supervision as a safety argument"),
    PageSpec("wawel", "ike", _s("collapsed"), "risk inside a closed <details>"),
    PageSpec("wawel", "cfd", _s("no_risk", "no_ad_label"), "two defects"),
    PageSpec("wawel", "fund", _s("perf", "forecast"), "tricky: performance and forecast, ok"),
    PageSpec("mazury", "bonds", _s("low_contrast"), "pale grey risk warning"),
    PageSpec("mazury", "etf", _s("english_risk"), "risk warning in English"),
    PageSpec("mazury", "fund", _s("perf_no_disclaimer", "perf_dominant"), "two defects"),
    PageSpec("mazury", "cfd", _s("knf", "secure_login"), "tricky: KNF and 'bezpieczne' apart"),
    PageSpec("mazury", "cfd", _s("mobile_clipped"), "risk cut on phones"),
    PageSpec("odra", "etf", _s(), "baseline compliant page"),
    PageSpec("odra", "bonds", _s("occluded"), "sticker covers the risk warning"),
    PageSpec("odra", "cfd", _s("knf_approval"), "suggests KNF approval"),
    PageSpec("odra", "ike", _s("tax_no_disclaimer"), "tax benefit without disclaimer"),
    PageSpec("odra", "cfd", _s("forecast_no_disclaimer"), "forecast without disclaimer"),
    PageSpec("pilica", "etf", _s("secure_login"), "tricky: long page, 'bezpieczne' login"),
    PageSpec("pilica", "bonds", _s("no_gains"), "tricky: info page, no gains"),
    PageSpec("pilica", "ike", _s("tax", "knf"), "tricky: tax disclaimer + factual KNF"),
    PageSpec("pilica", "fund", _s("perf", "forecast", "knf"), "tricky: everything disclosed"),
    PageSpec("pilica", "cfd", _s(), "baseline compliant CFD page"),
]


@dataclass(frozen=True)
class TextSpec:
    """A synthetic social post or text-only page for M1 or M3."""

    module: ModuleId
    label: Literal[0, 1]
    platform: Platform
    author: str
    text: str
    firm: str | None = None
    firm_on: Literal["author", "content"] = "content"
    note: str = ""
    rules: str = ""
    """Per-rule ground truth, e.g. `"2=fail 3=na"`; rules left out are not scored."""


def parse_rules(spec: str) -> dict[str, RuleLabel]:
    """Parse the compact `"<rule>=<pass|fail|na> ..."` notation of `TextSpec.rules`."""
    out: dict[str, RuleLabel] = {}
    for part in spec.split():
        rule_id, _, value = part.partition("=")
        if value not in ("pass", "fail", "na"):
            raise ValueError(f"bad rule label {part!r}")
        out[rule_id] = value  # type: ignore[assignment]
    return out


M1_POSTS: list[TextSpec] = [
    TextSpec("m1_third_party_ad", 1, "instagram", "@inwestujzkasia",
             "Od roku inwestuję w ETF-y przez Nordbrok 🚀 Z mojego linku w bio dostaniesz 3 "
             "miesiące bez prowizji! #współpraca #nordbrok", "nordbrok",
             note="referral link, labelled #współpraca", rules="2=pass 3=na"),
    TextSpec("m1_third_party_ad", 1, "instagram", "@inwestujzkasia",
             "Mój portfel w październiku +14%! 📈 Wszystko kupuję w aplikacji Sowa Maklerska, a "
             "z kodem KASIA50 dostaniesz 50 zł na start 💸", "sowa",
             note="promo code, no ad label, gains without risk", rules="2=fail 3=fail"),
    TextSpec("m1_third_party_ad", 1, "youtube", "Finanse Bez Ściemy",
             "Jak zacząć handel na złocie? Film powstał we współpracy z Odra Markets. Załóż konto: "
             "https://odramarkets.example/open?ref=fbs i odbierz bonus na start. CFD to "
             "instrumenty z dźwignią, możesz stracić cały kapitał.", "odra",
             note="sponsored video, affiliate link, has risk warning", rules="2=pass"),
    TextSpec("m1_third_party_ad", 1, "tiktok", "@trader.mateo",
             "Zarobiłem 2400 zł w tydzień na CFD na złocie 🔥 platforma Kopernik Trade, link w "
             "bio, kod MATEO100 i lecimy", "kopernik", note="gains, promo code, no label",
             rules="2=fail 3=fail"),
    TextSpec("m1_third_party_ad", 1, "facebook", "Klub Dywidendy",
             "Partnerem dzisiejszego webinaru jest Bałtyk Securities. Otwórz rachunek przez "
             "link https://baltyksecurities.example/konto?utm_source=klubdywidendy i odbierz "
             "pół roku bez opłat. Materiał sponsorowany.", "baltyk",
             note="partner webinar, utm link, labelled", rules="2=pass 3=na"),
    TextSpec("m1_third_party_ad", 1, "youtube", "Giełda dla Każdego",
             "Ranking kont maklerskich 2026 – które wybrać? W opisie linki afiliacyjne: Nordbrok "
             "https://nordbrok.example/konto?aff=gdk – zakładając konto z linku wspierasz kanał.",
             "nordbrok", note="ranking with affiliate links", rules="3=na"),
    TextSpec("m1_third_party_ad", 1, "instagram", "@mama.inwestuje",
             "Dzięki Tatra Fundusze odkładam na przyszłość dzieci 💛 Załóżcie konto z mojego "
             "linku, a dostaniecie bonus 100 zł. #reklama", "tatra",
             note="referral bonus, labelled #reklama", rules="2=pass 3=na"),
    TextSpec("m1_third_party_ad", 1, "tiktok", "@krypto.szymon",
             "Odra Markets daje 200% bonusu do depozytu!!! wchodzisz z linku w opisie i "
             "odbierasz, ja już podwoiłem kapitał 🚀", "odra",
             note="bonus, gains claim, no risk, no label", rules="2=fail 3=fail"),
    TextSpec("m1_third_party_ad", 1, "facebook", "Oszczędny Tata",
             "Polecam Wawel Broker – od 3 lat trzymam tam IKE. Kod polecający TATA2026 daje rok "
             "bez opłaty za prowadzenie IKE. Zapisz się, warto!", "wawel",
             note="referral code", rules="2=fail 3=na"),
    TextSpec("m1_third_party_ad", 0, "instagram", "@inwestujzkasia",
             "Czy ktoś ma doświadczenia z wypłatą środków z Nordbrok? Czekam już 5 dni roboczych "
             "😤 Dajcie znać w komentarzach.", "nordbrok", note="tricky: complaint",
             rules="2=na 3=na"),
    TextSpec("m1_third_party_ad", 0, "youtube", "Finanse Bez Ściemy",
             "Analiza wyników kwartalnych: Sowa Maklerska raportuje spadek przychodów o 12% r/r, "
             "a liczba rachunków wzrosła o 4%. Omawiam raport i komentarze zarządu.", "sowa",
             note="tricky: news about the firm", rules="2=na 3=na"),
    TextSpec("m1_third_party_ad", 0, "facebook", "Klub Dywidendy",
             "Uwaga: KNF wpisała na listę ostrzeżeń publicznych podmiot podszywający się pod "
             "Kopernik Trade. Sprawdzajcie domenę, zanim gdziekolwiek wpłacicie pieniądze.",
             "kopernik", note="tricky: warning about impersonation", rules="2=na 3=na"),
    TextSpec("m1_third_party_ad", 0, "tiktok", "@trader.mateo",
             "Dlaczego NIE polecam CFD początkującym? 74% rachunków traci pieniądze, nawet u "
             "dużych brokerów jak Odra Markets. Najpierw naucz się zarządzać ryzykiem.", "odra",
             note="tricky: critical, gains words absent", rules="2=na 3=na"),
    TextSpec("m1_third_party_ad", 0, "youtube", "Giełda dla Każdego",
             "Jak działa IKE i IKZE? Tłumaczę limity wpłat na 2026 rok. Tabele opłat Wawel Broker "
             "i Tatra Fundusze pokazuję poglądowo. Film nie jest sponsorowany i nie zawiera "
             "linków afiliacyjnych.", "wawel", note="tricky: education, explicit no sponsor",
             rules="2=na 3=na"),
    TextSpec("m1_third_party_ad", 0, "instagram", "@mama.inwestuje",
             "#reklama Nowa kolekcja ubranek od @maluszkowo 👶 Kod MAMA10 daje 10% rabatu! P.S. "
             "Pytaliście o konta w Nordbrok – opowiem w piątek, bez żadnych linków.", "nordbrok",
             note="tricky: ad for another product, firm only mentioned", rules="2=pass 3=na"),
    TextSpec("m1_third_party_ad", 0, "facebook", "Oszczędny Tata",
             "Bałtyk Securities zmienia tabelę opłat od 1 grudnia – prowizja za akcje zagraniczne "
             "rośnie do 0,29%. Info z komunikatu na ich stronie.", "baltyk",
             note="tricky: fee change news", rules="2=na 3=na"),
    TextSpec("m1_third_party_ad", 1, "facebook", "Młodzi Inwestują",
             "KONKURS 🎁 Otwórz rachunek w Mazury Capital z naszego linku do końca miesiąca i "
             "wygraj iPhone'a! Regulamin w pierwszym komentarzu.", "mazury",
             note="giveaway tied to opening an account, no label", rules="2=fail 3=na"),
    TextSpec("m1_third_party_ad", 1, "youtube", "Obligacje po Godzinach",
             "Sponsorem odcinka jest Pilica Inwestycje: obligacje korporacyjne z kuponem 9% "
             "rocznie, wypłacanym co kwartał. Link do zapisów w opisie.", "pilica",
             note="sponsored segment, gains without risk", rules="2=pass 3=fail"),
    TextSpec("m1_third_party_ad", 0, "facebook", "Młodzi Inwestują",
             "Pilica Inwestycje szuka młodszego analityka rynku obligacji do biura w Łodzi. "
             "Wymagania i formularz zgłoszeniowy na stronie kariery firmy.", "pilica",
             note="tricky: job offer from the firm", rules="2=na 3=na"),
    TextSpec("m1_third_party_ad", 0, "web", "porownajoplaty.example",
             "Porównaliśmy opłaty 12 domów maklerskich, w tym Mazury Capital i Sowa Maklerska. "
             "Zestawienie jest niezależne, nie zawiera linków partnerskich i nie jest "
             "sponsorowane.", "mazury", note="tricky: independent fee comparison",
             rules="2=na 3=na"),
]  # fmt: skip

M3_POSTS: list[TextSpec] = [
    TextSpec("m3_shadow_advisory", 1, "web", "zlotesygnaly.example",
             "Grupa VIP na Telegramie: codziennie 3 sygnały KUP/SPRZEDAJ na spółki z GPW i "
             "ETF-y. Abonament 149 zł miesięcznie. Powiemy Ci dokładnie, co kupić i kiedy "
             "sprzedać. Dołącz już dziś!", note="paid buy/sell signals",
             rules="76a=pass 76c=fail 76e=pass"),
    TextSpec("m3_shadow_advisory", 1, "web", "majatekpodkontrola.example",
             "Family office dla przedsiębiorców. Przygotujemy indywidualną strategię inwestycyjną "
             "dopasowaną do Twojej sytuacji i celów. Zarządzamy Twoim kapitałem: dobieramy akcje, "
             "obligacje i fundusze. Biuro w Warszawie, umów bezpłatną konsultację.",
             note="personalised strategy + portfolio management", rules="76a=fail 76e=fail"),
    TextSpec("m3_shadow_advisory", 1, "instagram", "@dywidendowy.mentor",
             "Konsultacje 1:1 (399 zł): przeanalizuję Twój portfel i powiem Ci, które akcje "
             "sprzedać, a które dokupić. Napisz DM z hasłem PORTFEL.",
             note="paid personal buy/sell advice", rules="76a=fail 76c=fail 76e=pass"),
    TextSpec("m3_shadow_advisory", 1, "facebook", "Akademia Tradera Pro",
             "Kopiuj moje transakcje! Daj mi dostęp do swojego rachunku, a ja będę zarządzać "
             "Twoim portfelem CFD w Twoim imieniu. Wynagrodzenie: 30% od zysku.",
             note="managing others' accounts", rules="76e=fail"),
    TextSpec("m3_shadow_advisory", 1, "tiktok", "@gieldowy.wilk",
             "W płatnej grupie (99 zł/mies.) podaję listę 5 spółek do kupienia na ten miesiąc, "
             "dobraną do Twojego budżetu. Kupuj, gdy dam sygnał, sprzedawaj, gdy napiszę.",
             note="paid personalised stock picks", rules="76a=fail 76c=fail 76e=pass"),
    TextSpec("m3_shadow_advisory", 1, "web", "inwestorprywatny.example",
             "Wypełnij ankietę profilu ryzyka, a w 48 godzin otrzymasz spersonalizowaną "
             "rekomendację: które ETF-y i obligacje skarbowe kupić za Twoje oszczędności. "
             "Cena usługi: 590 zł. Płatność BLIK.", note="questionnaire + personalised advice",
             rules="76a=fail 76c=fail 76e=pass"),
    TextSpec("m3_shadow_advisory", 1, "youtube", "Rynek bez Tajemnic",
             "Dołącz do programu mentoringowego: co tydzień mówię uczestnikom, co kupić, co "
             "sprzedać i co trzymać w ich portfelach. Indywidualne podejście do każdego. Zapisy: "
             "rynekbeztajemnic.example/mentoring", note="buy/sell/hold for participants",
             rules="76a=fail 76c=fail 76e=pass"),
    TextSpec("m3_shadow_advisory", 1, "web", "kapitalrodzinny.example",
             "Przejmujemy zarządzanie portfelem papierów wartościowych Twojej rodziny i "
             "rekomendujemy konkretne fundusze oraz obligacje dopasowane do Twoich potrzeb. "
             "Spotkania w Krakowie i Warszawie.", note="family office managing portfolios",
             rules="76a=fail 76c=fail 76e=fail"),
    TextSpec("m3_shadow_advisory", 0, "web", "edukacjafinansowa.example",
             "Czym jest ETF? Fundusz notowany na giełdzie odwzorowuje indeks, np. WIG20. "
             "Wyjaśniamy "
             "koszty, ryzyko i podatki. Artykuł ma charakter edukacyjny i nie stanowi "
             "rekomendacji ani porady inwestycyjnej.", note="tricky: education",
             rules="76a=pass 76c=pass 76e=pass"),
    TextSpec("m3_shadow_advisory", 0, "web", "sowamaklerska.example",
             "Doradztwo inwestycyjne w Sowa Maklerska: doradca przygotuje rekomendację "
             "dopasowaną do Twojej sytuacji i profilu ryzyka. Usługa świadczona na podstawie "
             "zezwolenia KNF.", firm="sowa", firm_on="author",
             note="tricky: licensed firm offering advice (registered with A5)",
             rules="76a=fail 76e=pass"),
    TextSpec("m3_shadow_advisory", 0, "youtube", "Rynek bez Tajemnic",
             "Przegląd tygodnia na GPW: WIG20 spadł o 2%, mocniejsze były banki. To nie jest "
             "rekomendacja – omawiam wyłącznie dane rynkowe i kalendarz wydarzeń.",
             note="tricky: market commentary", rules="76a=pass 76c=pass 76e=pass"),
    TextSpec("m3_shadow_advisory", 0, "web", "doradcapodatkowy.example",
             "Doradztwo podatkowe dla inwestorów: rozliczymy PIT-38 i dywidendy z zagranicy, "
             "dopasujemy rozliczenie do Twojej sytuacji. Nie świadczymy doradztwa "
             "inwestycyjnego.", note="tricky: tax advice, personalised but not investments",
             rules="76a=fail 76c=pass 76e=pass"),
    TextSpec("m3_shadow_advisory", 0, "instagram", "@dywidendowy.mentor",
             "Mój portfel dywidendowy w listopadzie – pokazuję, co sam kupiłem. Nie mówię Ci, "
             "co masz robić: każdy ma inną sytuację.", note="tricky: own portfolio disclosure",
             rules="76a=pass 76e=pass"),
    TextSpec("m3_shadow_advisory", 0, "web", "nieruchomoscipro.example",
             "Doradztwo przy zakupie mieszkania na wynajem: dobierzemy lokal do Twojego budżetu "
             "i oczekiwanej rentowności, negocjujemy cenę i umowę.",
             note="tricky: personalised property advice, no financial instruments",
             rules="76a=fail 76c=pass 76e=pass"),
    TextSpec("m3_shadow_advisory", 1, "facebook", "Spokojny Portfel",
             "Napisz w wiadomości, ile masz oszczędności i na jak długo, a dobiorę Ci gotowy "
             "portfel ETF: konkretne 3 fundusze i proporcje. Konsultacja 250 zł.",
             note="paid personalised ETF portfolio", rules="76a=fail 76c=fail 76e=pass"),
    TextSpec("m3_shadow_advisory", 0, "web", "kalkulatorinwestora.example",
             "Kalkulator procentu składanego: wpisz kwotę, okres i zakładaną stopę zwrotu, a "
             "zobaczysz wartość oszczędności. Narzędzie służy do samodzielnych obliczeń i nie "
             "stanowi porady inwestycyjnej.", note="tricky: self-service calculator",
             rules="76a=pass 76c=pass 76e=pass"),
]  # fmt: skip


def _slug(text: str) -> str:
    keep = "".join(c if c.isalnum() else "-" for c in text.lower())
    return "-".join(p for p in keep.split("-") if p)[:40]


def m2_item_id(index: int) -> str:
    """Stable id of the n-th synthetic M2 page."""
    return f"syn-m2-{index + 1:03d}"


def m2_items(texts: dict[str, str]) -> list[GoldenItem]:
    """Golden items for the M2 pages; `texts` maps item id to the page text."""
    items: list[GoldenItem] = []
    for i, spec in enumerate(M2_PAGES):
        item_id = m2_item_id(i)
        firm = FIRMS[spec.firm]
        labels = rule_labels(spec)
        url = f"https://{firm.domains[0]}/oferta/{item_id}.html"
        items.append(
            GoldenItem(
                id=item_id,
                module="m2_risk_disclosure",
                label=1 if "fail" in labels.values() else 0,
                rule_labels=labels,
                origin="synthetic",
                provenance=GENERATOR,
                group=f"firm:{spec.firm}",
                post=GoldenPost(
                    platform="web",
                    collector="synthetic",
                    external_id=url,
                    url=url,
                    author=firm.domains[0],
                    text=texts[item_id],
                ),
                html_path=f"synthetic/pages/{item_id}.html",
                render_path=f"synthetic/render/{item_id}.json",
                firm_matches=[firm_match(spec.firm, "author")],
                register_status="registered",
                labeler="generator",
                confidence=1.0,
                note=f"{spec.topic}; {', '.join(sorted(spec.flags)) or 'no flags'}; {spec.note}",
            )
        )
    return items


def text_items() -> list[GoldenItem]:
    """Golden items for the synthetic M1 and M3 posts."""
    items: list[GoldenItem] = []
    for prefix, specs in (("syn-m1", M1_POSTS), ("syn-m3", M3_POSTS)):
        for i, spec in enumerate(specs):
            url = (
                f"https://{spec.author}/{_slug(spec.text)}"
                if spec.platform == "web"
                else f"https://{spec.platform}.example/{_slug(spec.author)}/{i + 1}"
            )
            matches: list[FirmMatch] = []
            if spec.firm:
                matches = [firm_match(spec.firm, spec.firm_on)]
            status = "registered" if spec.firm_on == "author" and spec.firm else "not_registered"
            items.append(
                GoldenItem(
                    id=f"{prefix}-{i + 1:03d}",
                    module=spec.module,
                    label=spec.label,
                    origin="synthetic",
                    provenance=GENERATOR,
                    group=f"author:{_slug(spec.author)}",
                    post=GoldenPost(
                        platform=spec.platform,
                        collector="synthetic",
                        external_id=url,
                        url=url,
                        author=spec.author,
                        text=spec.text,
                    ),
                    rule_labels=parse_rules(spec.rules),
                    firm_matches=matches,
                    register_status=status,
                    labeler="generator",
                    confidence=1.0,
                    note=spec.note,
                )
            )
    return items
