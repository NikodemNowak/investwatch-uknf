"""Render rules 4-8 and 13: pure functions over a `RenderSnapshot`.

The collector only records layout facts per viewport; every judgement lives here so it can be
unit-tested on stored snapshots. Every result carries `Evidence` with the viewport, the block's
bounding box (page coordinates) and the measurements, so the UI can draw a box on the screenshot.

Risk blocks are text blocks matching the `risk_warning` lexicon; gains blocks match `gains_claim`.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence

from ..schemas import Evidence, RenderSnapshot, TextBlock, Viewport
from .registry import Outcome, load_lexicon

FONT_RATIO_MIN = 0.95
"""Rule 4: risk font may be at most 5% smaller than the dominant font."""
WCAG_MIN_CONTRAST = 4.5
OPACITY_MIN = 0.6
MIN_FONT_PX = 12.0
LOW_ON_PAGE = 0.85
"""Rule 6: a block below this fraction of the page height counts as hidden low."""
FIRST_SCREEN_PX: dict[Viewport, float] = {"desktop": 900.0, "tablet": 1180.0, "phone": 844.0}
VIEWPORT_ORDER: tuple[Viewport, ...] = ("desktop", "tablet", "phone")
VIEWPORT_PL: dict[Viewport, str] = {"desktop": "komputer", "tablet": "tablet", "phone": "telefon"}
MAX_EVIDENCE = 3
QUOTE_CHARS = 160

_RISK_LINK = re.compile(
    r"ryzyk|ostrzeż|informacj\w* (?:prawn|o ryzyku)|nota prawna|zastrzeżeni|disclaimer|risk",
    re.IGNORECASE,
)
_TRIGGER_TAGS = {"a", "button", "summary"}


# Helpers


def matches(block: TextBlock, category: str) -> bool:
    """True when the block's text matches a lexicon category."""
    return any(p.search(block.text) for p in load_lexicon()[category])


def is_risk(block: TextBlock) -> bool:
    """Block contains a risk warning."""
    return matches(block, "risk_warning")


def shown(block: TextBlock) -> bool:
    """Rendered and not inside a collapsed container."""
    return block.visible and not block.in_collapsed


def _hex_rgb(color: str) -> tuple[float, float, float]:
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        raise ValueError(f"not a #rrggbb colour: {color!r}")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _luminance(color: str) -> float:
    def channel(c: float) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in _hex_rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.x contrast ratio between two `#rrggbb` colours (1.0 to 21.0)."""
    a, b = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def dominant_font_px(blocks: Iterable[TextBlock]) -> float | None:
    """Median font size weighted by text length (what most of the text is set in)."""
    weighted = sorted((b.font_px, len(b.text)) for b in blocks if b.text.strip())
    total = sum(w for _, w in weighted)
    if not total:
        return None
    acc = 0
    for font, w in weighted:
        acc += w
        if acc * 2 >= total:
            return font
    return weighted[-1][0]


def _dominant(blocks: Sequence[TextBlock]) -> float | None:
    body = [b for b in blocks if shown(b) and not is_risk(b)]
    return dominant_font_px(body or [b for b in blocks if not is_risk(b)])


def _quote(block: TextBlock) -> str:
    text = " ".join(block.text.split())
    return text if len(text) <= QUOTE_CHARS else text[: QUOTE_CHARS - 1].rstrip() + "…"


def _ev(block: TextBlock, viewport: Viewport, **measurements: float | str) -> Evidence:
    return Evidence(
        quote=_quote(block), viewport=viewport, bbox=block.bbox, measurements=dict(measurements)
    )


def _pl(x: float, digits: int = 2) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def _contrast_pl(contrast: float) -> str:
    """Contrast rounded down to one decimal, as the dashboard shows it (1.45 -> "1,4")."""
    return _pl(math.floor(contrast * 10) / 10, 1)


def _primary(render: RenderSnapshot) -> Viewport | None:
    return next((v for v in VIEWPORT_ORDER if render.viewports.get(v)), None)


def _risks(render: RenderSnapshot, viewport: Viewport) -> list[TextBlock]:
    return [b for b in render.viewports.get(viewport, []) if is_risk(b)]


def _most_specific(blocks: Iterable[TextBlock]) -> list[TextBlock]:
    """Shown blocks first, then hidden ones by the size of the box they point at.

    Hidden text carries the box of its closest painted container; the smallest such box (e.g. a
    `<details>` line rather than the whole footer) is the most useful one to draw.
    """
    return sorted(blocks, key=lambda b: (not shown(b), b.bbox[2] * b.bbox[3]))


def has_risk_block(render: RenderSnapshot) -> bool:
    """Any viewport contains a risk block."""
    return any(_risks(render, v) for v in render.viewports)


def _no_risk_block() -> Outcome:
    return Outcome(
        "unknown",
        0.0,
        "Tekst zawiera ostrzeżenie, ale nie udało się go zlokalizować w renderze strony.",
    )


def _no_viewport() -> Outcome:
    return Outcome("unknown", 0.0, "RenderSnapshot nie zawiera żadnego widoku.")


def _ratio(block: TextBlock, dominant: float | None) -> float:
    return round(block.font_px / dominant, 3) if dominant else 1.0


def _flag(value: bool) -> str:
    return "true" if value else "false"


# Rule 4


def font_size(render: RenderSnapshot) -> Outcome:
    """Rule 4: risk font vs the dominant (length-weighted median) font in the main viewport."""
    vp = _primary(render)
    if vp is None:
        return _no_viewport()
    blocks = render.viewports[vp]
    risks = _risks(render, vp)
    if not risks:
        return _no_risk_block()
    dominant = _dominant(blocks)
    candidates = [b for b in risks if shown(b)] or risks
    ranked = sorted(candidates, key=lambda b: (-_ratio(b, dominant), -len(b.text)))
    best = ranked[0]
    ratio = _ratio(best, dominant)
    dom = dominant or best.font_px
    evidence = [
        _ev(b, vp, risk_font_px=b.font_px, dominant_font_px=dom, ratio=_ratio(b, dominant))
        for b in ranked[:MAX_EVIDENCE]
    ]
    if ratio < FONT_RATIO_MIN:
        return Outcome(
            "fail",
            0.95 if ratio < 0.8 else 0.75,
            f"Czcionka ostrzeżenia {_pl(best.font_px, 0)} px przy dominującej {_pl(dom, 0)} px "
            f"(stosunek {_pl(ratio)}, wymagane co najmniej {_pl(FONT_RATIO_MIN)}).",
            evidence,
        )
    return Outcome(
        "pass",
        0.85,
        f"Czcionka ostrzeżenia {_pl(best.font_px, 0)} px nie jest mniejsza od dominującej "
        f"{_pl(dom, 0)} px (stosunek {_pl(ratio)}).",
        evidence[:1],
    )


# Rule 5


def _exposure_problems(block: TextBlock) -> list[str]:
    problems = []
    contrast = contrast_ratio(block.color, block.background)
    if contrast < WCAG_MIN_CONTRAST:
        problems.append(
            f"kontrast {_contrast_pl(contrast)}:1 ({block.color} na {block.background}) poniżej "
            f"progu {_pl(WCAG_MIN_CONTRAST, 1)}:1"
        )
    if block.occluded:
        problems.append("tekst jest przesłonięty innym elementem")
    if block.opacity < OPACITY_MIN:
        problems.append(f"przezroczystość {_pl(block.opacity)} (minimum {_pl(OPACITY_MIN, 1)})")
    return problems


def exposure(render: RenderSnapshot) -> Outcome:
    """Rule 5: WCAG contrast, occlusion and opacity of the risk block."""
    vp = _primary(render)
    if vp is None:
        return _no_viewport()
    risks = _risks(render, vp)
    if not risks:
        return _no_risk_block()
    candidates = [b for b in risks if shown(b)] or risks
    ranked = sorted(
        candidates,
        key=lambda b: (
            len(_exposure_problems(b)),
            -contrast_ratio(b.color, b.background),
            -len(b.text),
        ),
    )

    def ev(b: TextBlock) -> Evidence:
        return _ev(
            b,
            vp,
            contrast=round(contrast_ratio(b.color, b.background), 2),
            color=b.color,
            background=b.background,
            opacity=round(b.opacity, 2),
            occluded=_flag(b.occluded),
        )

    best = ranked[0]
    problems = _exposure_problems(best)
    if problems:
        return Outcome(
            "fail",
            0.85,
            "Ostrzeżenie o ryzyku jest słabo eksponowane: " + "; ".join(problems) + ".",
            [ev(b) for b in ranked[:MAX_EVIDENCE]],
        )
    return Outcome(
        "pass",
        0.8,
        f"Ostrzeżenie ma kontrast "
        f"{_contrast_pl(contrast_ratio(best.color, best.background))}:1, nie jest przesłonięte "
        "ani przezroczyste.",
        [ev(best)],
    )


# Rule 6


def _low(block: TextBlock, viewport: Viewport) -> bool:
    below_first_screen = block.bbox[1] > FIRST_SCREEN_PX[viewport]
    return block.in_footer or (block.y_ratio > LOW_ON_PAGE and below_first_screen)


def hidden_low(render: RenderSnapshot) -> Outcome:
    """Rule 6: risk only in footer / legal notes / bottom of page while gains are up front."""
    vp = _primary(render)
    if vp is None:
        return _no_viewport()
    blocks = render.viewports[vp]
    risks = _risks(render, vp)
    if not risks:
        return _no_risk_block()
    gains_up_front = [
        b
        for b in blocks
        if shown(b) and matches(b, "gains_claim") and b.bbox[1] < FIRST_SCREEN_PX[vp]
    ]
    prominent = [b for b in risks if not _low(b, vp)]

    def ev(b: TextBlock) -> Evidence:
        return _ev(
            b,
            vp,
            y_ratio=round(b.y_ratio, 3),
            in_footer=_flag(b.in_footer),
            tag_path=b.tag_path,
        )

    if prominent:
        best = min(prominent, key=lambda b: b.bbox[1])
        return Outcome(
            "pass",
            0.8,
            f"Ostrzeżenie jest w treści strony (na {_pl(best.y_ratio * 100, 0)}% wysokości), "
            "nie tylko w stopce.",
            [ev(best)],
        )
    ordered = _most_specific(risks)
    evidence = [ev(b) for b in ordered[:MAX_EVIDENCE]]
    first = ordered[0]
    where = "w stopce / przypisach" if first.in_footer else "w dolnej części strony"
    if gains_up_front:
        g = gains_up_front[0]
        evidence.append(_ev(g, vp, y_ratio=round(g.y_ratio, 3), role="gains_claim"))
        return Outcome(
            "fail",
            0.9,
            f"Ostrzeżenie jest tylko {where} (na {_pl(first.y_ratio * 100, 0)}% wysokości "
            f"strony), a obietnica zysku „{_quote(g)}” jest na pierwszym ekranie.",
            evidence,
        )
    return Outcome(
        "pass",
        0.5,
        f"Ostrzeżenie jest {where}, ale twierdzenia o zysku nie są na pierwszym ekranie.",
        evidence[:1],
    )


# Rule 7


def _tag(block: TextBlock) -> str:
    last = block.tag_path.rsplit(">", 1)[-1]
    return last.split(".", 1)[0].split("#", 1)[0].lower()


def _in_trigger(block: TextBlock) -> bool:
    tags = {part.split(".", 1)[0].split("#", 1)[0].lower() for part in block.tag_path.split(">")}
    return bool(tags & _TRIGGER_TAGS)


def _triggers(blocks: Sequence[TextBlock]) -> list[TextBlock]:
    """Visible links / buttons / summaries that lead to the warning."""
    return [b for b in blocks if shown(b) and _in_trigger(b) and _RISK_LINK.search(b.text)] or [
        b for b in blocks if shown(b) and _tag(b) == "summary"
    ]


def one_click(render: RenderSnapshot) -> Outcome:
    """Rule 7: risk text readable without a click in every viewport (not collapsed, not a link)."""
    vp = _primary(render)
    if vp is None:
        return _no_viewport()
    for view in (v for v in VIEWPORT_ORDER if render.viewports.get(v)):
        risks = _risks(render, view)
        if not risks or any(shown(b) for b in risks):
            continue
        triggers = _triggers(render.viewports[view])
        evidence = [
            _ev(b, view, in_collapsed=_flag(b.in_collapsed), visible=_flag(b.visible))
            for b in _most_specific(risks)[:MAX_EVIDENCE]
        ]
        evidence += [_ev(t, view, role="trigger") for t in triggers[:1]]
        how = f" pod elementem „{_quote(triggers[0])}”" if triggers else ""
        where = "" if view == vp else f" (widok: {VIEWPORT_PL[view]})"
        return Outcome(
            "fail",
            0.9,
            f"Ostrzeżenie jest w kodzie strony, ale ukryte (zwinięte){how}{where}: czytelnik "
            "musi kliknąć, żeby je zobaczyć.",
            evidence,
        )
    blocks = render.viewports[vp]
    visible = [b for b in _risks(render, vp) if shown(b)]
    if visible:
        best = max(visible, key=lambda b: len(b.text))
        return Outcome(
            "pass",
            0.85,
            "Ostrzeżenie jest widoczne bez rozwijania i klikania.",
            [_ev(best, vp, in_collapsed="false", visible="true")],
        )
    links = [b for b in blocks if shown(b) and _in_trigger(b) and _RISK_LINK.search(b.text)]
    if links:
        return Outcome(
            "fail",
            0.75,
            f"Jedynym śladem ostrzeżenia jest odnośnik „{_quote(links[0])}”.",
            [_ev(links[0], vp, role="link")],
        )
    return Outcome("na", 0.6, "Na stronie nie ma ostrzeżenia o ryzyku (zob. reguła 3).")


# Rule 8


def _viewport_check(
    render: RenderSnapshot, vp: Viewport, reference_ratio: float
) -> tuple[bool, TextBlock, list[str], float]:
    blocks = render.viewports[vp]
    dominant = _dominant(blocks)
    min_ratio = min(1.0, reference_ratio) * FONT_RATIO_MIN

    def problems(b: TextBlock) -> list[str]:
        out = []
        if not shown(b):
            out.append("niewidoczne bez rozwijania")
        if b.clipped:
            out.append("ucięte")
        if b.occluded:
            out.append("przesłonięte")
        if b.font_px < MIN_FONT_PX:
            out.append(f"czcionka {_pl(b.font_px, 0)} px (minimum {_pl(MIN_FONT_PX, 0)} px)")
        r = _ratio(b, dominant)
        if r < min_ratio:
            out.append(f"stosunek do tekstu głównego spada do {_pl(r)}")
        return out

    ranked = sorted(
        _risks(render, vp),
        key=lambda b: (len(problems(b)), not shown(b), -b.font_px, b.bbox[2] * b.bbox[3]),
    )
    best = ranked[0]
    found = problems(best)
    return (not found, best, found, _ratio(best, dominant))


def responsive(render: RenderSnapshot) -> Outcome:
    """Rule 8: in every viewport the risk block is visible, unclipped, >= 12 px, ratio kept."""
    vps = [v for v in VIEWPORT_ORDER if render.viewports.get(v)]
    if not vps:
        return _no_viewport()
    if not any(_risks(render, v) for v in vps):
        return _no_risk_block()
    reference = 1.0
    ref_vp = vps[0]
    if _risks(render, ref_vp):
        reference = _viewport_check(render, ref_vp, 1.0)[3]
    passed: list[Evidence] = []
    failed: list[Evidence] = []
    reasons: list[str] = []
    failing: list[str] = []
    for vp in vps:
        if not _risks(render, vp):
            reasons.append(f"{VIEWPORT_PL[vp]}: brak ostrzeżenia")
            failing.append(vp)
            continue
        ok, block, problems, ratio = _viewport_check(render, vp, reference)
        ev = _ev(
            block,
            vp,
            risk_font_px=block.font_px,
            ratio=ratio,
            visible=_flag(shown(block)),
            clipped=_flag(block.clipped),
        )
        if ok:
            passed.append(ev)
        else:
            failed.append(ev)
            failing.append(vp)
            reasons.append(f"{VIEWPORT_PL[vp]}: {', '.join(problems)}")
    if reasons:
        # Name only the failing devices (the UI titles the problem with them).
        shown_ev = [
            e.model_copy(
                update={"measurements": {**e.measurements, "failed_viewports": ",".join(failing)}}
            )
            for e in (failed or passed[:1])
        ]
        return Outcome(
            "fail",
            0.85,
            "Ostrzeżenie jest nieczytelne lub go brak (" + "; ".join(reasons) + ").",
            shown_ev,
        )
    return Outcome(
        "pass",
        0.8,
        "Ostrzeżenie jest widoczne, nieucięte i czytelne na komputerze, tablecie i telefonie.",
        passed,
    )


# Rule 13


def past_performance_dominance(render: RenderSnapshot) -> Outcome:
    """Rule 13: the most prominent element on the first screen is not past performance."""
    vp = _primary(render)
    if vp is None:
        return _no_viewport()
    first_screen = [b for b in render.viewports[vp] if shown(b) and b.bbox[1] < FIRST_SCREEN_PX[vp]]
    if not first_screen:
        return Outcome("unknown", 0.0, "Brak widocznego tekstu na pierwszym ekranie.")
    top = min(first_screen, key=lambda b: (-b.font_px, b.bbox[1]))
    dominant = _dominant(render.viewports[vp]) or top.font_px
    ev = _ev(top, vp, font_px=top.font_px, dominant_font_px=dominant)
    if matches(top, "past_performance"):
        return Outcome(
            "fail",
            0.8,
            f"Najbardziej wyeksponowanym elementem ({_pl(top.font_px, 0)} px) jest wynik "
            f"historyczny „{_quote(top)}”.",
            [ev],
        )
    return Outcome(
        "pass",
        0.6,
        f"Najbardziej wyeksponowany element („{_quote(top)}”) nie jest wynikiem historycznym.",
        [ev],
    )
