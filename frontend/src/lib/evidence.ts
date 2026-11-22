import type { BBox, RuleResult, TextBlock, Viewport } from "@/api/types";

/** One region on the page with every rule whose evidence points at it. */
export interface EvidenceBox {
  ruleIds: string[];
  /** True when at least one of the rules failed (box drawn as a violation). */
  failed: boolean;
  viewport: Viewport;
  bbox: BBox;
}

/** Viewport layout widths used by the renderer (plan 3.9). */
export const VIEWPORT_WIDTH: Record<Viewport, number> = { desktop: 1440, tablet: 820, phone: 390 };

/** Located evidence grouped by viewport and bbox, so shared regions get one labelled box. */
export function evidenceBoxes(rules: readonly RuleResult[]): EvidenceBox[] {
  const byKey = new Map<string, EvidenceBox>();
  for (const rule of rules) {
    for (const evidence of rule.evidence) {
      if (!evidence.bbox || !evidence.viewport) continue;
      const key = `${evidence.viewport}|${evidence.bbox.join(",")}`;
      const box = byKey.get(key) ?? {
        ruleIds: [],
        failed: false,
        viewport: evidence.viewport,
        bbox: evidence.bbox,
      };
      if (!box.ruleIds.includes(rule.rule_id)) box.ruleIds.push(rule.rule_id);
      box.failed ||= rule.status === "fail";
      byKey.set(key, box);
    }
  }
  return [...byKey.values()];
}

/** First viewport in which a rule has located evidence. */
export function viewportOfRule(rules: readonly RuleResult[], ruleId: string): Viewport | undefined {
  return evidenceBoxes(rules).find((box) => box.ruleIds.includes(ruleId))?.viewport;
}

/** First failed rule that has evidence located on the page (default selection). */
export function firstLocatedFailure(rules: readonly RuleResult[]): string | null {
  const rule = rules.find(
    (r) => r.status === "fail" && r.evidence.some((e) => e.bbox && e.viewport),
  );
  return rule?.rule_id ?? null;
}

/** Font size carrying the most characters on the page, i.e. the "main text" size. */
export function dominantFontPx(blocks: readonly TextBlock[]): number | undefined {
  const chars = new Map<number, number>();
  for (const block of blocks) {
    chars.set(block.font_px, (chars.get(block.font_px) ?? 0) + block.text.length);
  }
  let best: number | undefined;
  let bestChars = -1;
  for (const [px, count] of chars) {
    if (count > bestChars) [best, bestChars] = [px, count];
  }
  return best;
}

/** Page region shown around a piece of evidence: padded, clamped to the page. */
export function cropAround(
  bbox: BBox,
  pageWidth: number,
  pageHeight: number,
  pad = { x: 16, y: 40 },
): BBox {
  const [x, y, w, h] = bbox;
  const left = Math.max(0, x - pad.x);
  const top = Math.max(0, y - pad.y);
  const right = Math.min(pageWidth, x + w + pad.x);
  const bottom = Math.min(pageHeight, y + h + pad.y);
  return [left, top, right - left, bottom - top];
}

/** `bbox` clipped to the page, so a region reported past the edge is drawn inside the image. */
export function clampBox(bbox: BBox, pageWidth: number, pageHeight: number): BBox {
  const [x, y, w, h] = bbox;
  const left = Math.min(Math.max(0, x), pageWidth);
  const top = Math.min(Math.max(0, y), pageHeight);
  const right = Math.max(left, Math.min(pageWidth, x + w));
  const bottom = Math.max(top, Math.min(pageHeight, y + h));
  return [left, top, right - left, bottom - top];
}

/** Where and how much the screenshot panel shows (panel px; page drawn `pageWidth` wide). */
export interface FocusView {
  /** Panel px per page CSS px. */
  zoom: number;
  pageWidth: number;
  /** Left margin that centres a page narrower than the panel. */
  inset: number;
  height: number;
  left: number;
  top: number;
}

/** Share of the panel width a wide evidence region spans. */
const FOCUS_SPAN = 0.8;
/** Panel px kept above and below the region (room for its markers). */
const FOCUS_PAD_Y = 56;
/** Shortest crop, so a one-line region still shows some surroundings. */
const FOCUS_MIN_HEIGHT = 180;

/**
 * Tight crop of the page around `bbox`: a wide region spans ~80 % of the panel, a narrow one is
 * magnified up to `maxZoom`; the whole region stays inside the frame with a little context.
 */
export function focusView(
  bbox: BBox | null,
  pageWidth: number,
  pageHeight: number,
  panelWidth: number,
  maxHeight: number,
  maxZoom = 2,
): FocusView {
  const fitZoom = Math.min(maxZoom, panelWidth / pageWidth);
  if (!bbox) {
    const drawn = pageWidth * fitZoom;
    return {
      zoom: fitZoom,
      pageWidth: drawn,
      inset: Math.max(0, (panelWidth - drawn) / 2),
      height: Math.round(Math.min(maxHeight, pageHeight * fitZoom)),
      left: 0,
      top: 0,
    };
  }
  const [x, y, w, h] = clampBox(bbox, pageWidth, pageHeight);
  const cropWidth = Math.min(pageWidth, Math.max(w / FOCUS_SPAN, panelWidth / maxZoom));
  let zoom = Math.min(maxZoom, panelWidth / cropWidth);
  // A tall region is shrunk until it fits the frame height.
  if (h > 0) zoom = Math.min(zoom, Math.max(1, maxHeight - 2 * FOCUS_PAD_Y) / h);
  const drawnWidth = pageWidth * zoom;
  const drawnHeight = pageHeight * zoom;
  const height = Math.round(
    Math.min(drawnHeight, maxHeight, Math.max(FOCUS_MIN_HEIGHT, h * zoom + 2 * FOCUS_PAD_Y)),
  );
  const inset = Math.max(0, (panelWidth - drawnWidth) / 2);
  const clamp = (v: number, max: number) => Math.round(Math.max(0, Math.min(v, Math.max(0, max))));
  const left = clamp((x + w / 2) * zoom - panelWidth / 2, drawnWidth - panelWidth);
  const top = clamp((y + h / 2) * zoom - height / 2, drawnHeight - height);
  return { zoom, pageWidth: drawnWidth, inset, height, left, top };
}

/** Axis-aligned rectangle in panel px. */
export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Placed group of numbered markers for one box. */
export interface MarkerSpot extends Rect {
  /** Badges side by side (above/below) or stacked (left/right). */
  direction: "row" | "column";
}

/** Badge diameter and gap between badges (panel px), matching `.shot__badge`. */
export const BADGE = 24;
const BADGE_GAP = 4;
/** Distance between a box and its markers, and the clearance kept around other items. */
const MARKER_OFFSET = 8;
const CLEARANCE = 3;

function intersects(a: Rect, b: Rect): boolean {
  return (
    a.x < b.x + b.w + CLEARANCE &&
    b.x < a.x + a.w + CLEARANCE &&
    a.y < b.y + b.h + CLEARANCE &&
    b.y < a.y + a.h + CLEARANCE
  );
}

function inside(a: Rect, bounds: Rect): boolean {
  return (
    a.x >= bounds.x &&
    a.y >= bounds.y &&
    a.x + a.w <= bounds.x + bounds.w &&
    a.y + a.h <= bounds.y + bounds.h
  );
}

/**
 * Positions of the marker groups (one per box, `counts[i]` badges) so that no group overlaps a
 * box or another group: tries right, left, above, below; else stacks further above or below.
 * Spots inside `preferred` (the visible crop) win over spots elsewhere on the page.
 */
export function layoutMarkers(
  boxes: readonly Rect[],
  counts: readonly number[],
  page: Rect,
  preferred: Rect = page,
): MarkerSpot[] {
  const placed: Rect[] = [];
  return boxes.map((box, index) => {
    const n = Math.max(1, counts[index] ?? 1);
    const long = n * BADGE + (n - 1) * BADGE_GAP;
    const beside = (direction: MarkerSpot["direction"]): MarkerSpot[] => {
      const w = direction === "row" ? long : BADGE;
      const h = direction === "row" ? BADGE : long;
      const y = box.y + box.h / 2 - h / 2;
      return [
        { x: box.x + box.w + MARKER_OFFSET, y, w, h, direction },
        { x: box.x - MARKER_OFFSET - w, y, w, h, direction },
      ];
    };
    const aboveBelow: MarkerSpot[] = [
      { x: box.x, y: box.y - MARKER_OFFSET - BADGE, w: long, h: BADGE, direction: "row" },
      { x: box.x, y: box.y + box.h + MARKER_OFFSET, w: long, h: BADGE, direction: "row" },
    ];
    // Up to two badges stack beside the box; more read better as a row (a tall column is noisy).
    const candidates: MarkerSpot[] =
      n <= 2
        ? [...beside("column"), ...aboveBelow]
        : [...beside("row"), ...aboveBelow, ...beside("column")];
    const step = BADGE + BADGE_GAP;
    for (let k = 1; k <= 8; k++) {
      candidates.push(
        {
          x: box.x,
          y: box.y - MARKER_OFFSET - BADGE - k * step,
          w: long,
          h: BADGE,
          direction: "row",
        },
        {
          x: box.x,
          y: box.y + box.h + MARKER_OFFSET + k * step,
          w: long,
          h: BADGE,
          direction: "row",
        },
      );
    }
    const free = (spot: Rect, bounds: Rect) =>
      inside(spot, bounds) &&
      !boxes.some((other) => intersects(spot, other)) &&
      !placed.some((other) => intersects(spot, other));
    const spot = candidates.find((c) => free(c, preferred)) ??
      candidates.find((c) => free(c, page)) ?? {
        // Nowhere free: tuck the group into the box's top-right corner.
        x: Math.max(page.x, box.x + box.w - long - CLEARANCE),
        y: box.y + CLEARANCE,
        w: long,
        h: BADGE,
        direction: "row" as const,
      };
    placed.push(spot);
    return spot;
  });
}

/** Overlap of two boxes relative to the smaller one (1 = one contains the other). */
export function overlapRatio(a: BBox, b: BBox): number {
  const w = Math.min(a[0] + a[2], b[0] + b[2]) - Math.max(a[0], b[0]);
  const h = Math.min(a[1] + a[3], b[1] + b[3]) - Math.max(a[1], b[1]);
  if (w <= 0 || h <= 0) return 0;
  return (w * h) / Math.max(1, Math.min(a[2] * a[3], b[2] * b[3]));
}

/** Rendered text block that the evidence region points at (largest overlap), if any. */
export function blockAt(blocks: readonly TextBlock[], bbox: BBox): TextBlock | undefined {
  let best: TextBlock | undefined;
  let bestOverlap = 0.5;
  for (const block of blocks) {
    const o = overlapRatio(block.bbox, bbox);
    if (o > bestOverlap) [best, bestOverlap] = [block, o];
  }
  return best;
}

/**
 * Region of the actual text inside an element box: a single line of short text is trimmed to
 * its measured width (left-aligned), so a short warning in a wide container is not shown as a
 * long empty strip. Multi-line text fills its box.
 */
export function textBox(
  bbox: BBox,
  text: string,
  fontPx: number,
  measure: (text: string, fontPx: number) => number,
): BBox {
  const [x, y, w, h] = bbox;
  if (!text.trim() || h > fontPx * 2) return bbox;
  const width = measure(text.trim(), fontPx) * 1.08 + fontPx;
  return [x, y, Math.min(w, Math.max(width, fontPx * 4)), h];
}

/** Smallest on-screen size at which magnified text reads comfortably (panel px). */
export const LEGIBLE_PX = 14;

/**
 * Magnification of the evidence: at least enough to show `fontPx` text at `LEGIBLE_PX`, more
 * (up to 2x) when the text is short enough to fit, never above `maxZoom`; rounded up to 0.1.
 */
export function magnifierZoom(
  fontPx: number | undefined,
  textWidth: number,
  viewWidth: number,
  maxZoom = 3,
): number {
  const need = fontPx ? LEGIBLE_PX / fontPx : 1;
  const fit = textWidth > 0 ? viewWidth / textWidth : 1;
  const zoom = Math.min(maxZoom, Math.max(need, Math.min(fit, 2)));
  return Math.ceil(zoom * 10 - 1e-6) / 10;
}

/** A visible block set in the page's main font size: the "this is normal text" sample. */
export function sampleBlock(
  blocks: readonly TextBlock[],
  fontPx: number | undefined,
): TextBlock | undefined {
  if (fontPx === undefined) return undefined;
  const candidates = blocks.filter(
    (b) =>
      b.visible &&
      !b.occluded &&
      !b.in_collapsed &&
      Math.abs(b.font_px - fontPx) < 0.5 &&
      b.text.trim().length >= 20,
  );
  // Plain body copy (dark on light) reads as "normal text"; a banner in white on blue does not.
  const plain = candidates.filter((b) => !b.in_footer && isLight(b.background));
  return plain[0] ?? candidates.find((b) => !b.in_footer) ?? candidates[0];
}

/** True for a light CSS colour (`#rgb`, `#rrggbb`, `rgb()`/`rgba()`); unknown counts as light. */
export function isLight(color: string): boolean {
  let rgb: number[] | undefined;
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(color.trim());
  if (hex?.[1]) {
    const h = hex[1].length === 3 ? [...hex[1]].map((c) => c + c).join("") : hex[1];
    rgb = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  } else {
    const m = /rgba?\(([^)]+)\)/i.exec(color);
    const parts = m?.[1]?.split(",").map((v) => parseFloat(v));
    if (parts && parts.length >= 3) {
      // Fully transparent backgrounds show the (white) page behind them.
      if (parts.length >= 4 && parts[3] === 0) return true;
      rgb = parts.slice(0, 3);
    }
  }
  if (!rgb) return true;
  const [r = 255, g = 255, b = 255] = rgb;
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.6;
}

/** One drawn evidence region of the screenshot panel, with the numbers of its problems. */
export interface ShotBox {
  key: string;
  bbox: BBox;
  numbers: number[];
  ruleIds: string[];
  /** Only non-severe problems point here (drawn amber, not red). */
  soft: boolean;
}
