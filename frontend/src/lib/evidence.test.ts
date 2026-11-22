import { describe, expect, it } from "vitest";
import type { TextBlock } from "@/api/types";
import {
  BADGE,
  blockAt,
  clampBox,
  focusView,
  isLight,
  layoutMarkers,
  magnifierZoom,
  sampleBlock,
  textBox,
} from "@/lib/evidence";
import type { Rect } from "@/lib/evidence";

function overlaps(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

describe("clampBox", () => {
  it("clips a region reported past the page edge", () => {
    expect(clampBox([1300, 10, 400, 20], 1440, 2000)).toEqual([1300, 10, 140, 20]);
    expect(clampBox([-10, 1990, 50, 30], 1440, 2000)).toEqual([0, 1990, 40, 10]);
  });
});

describe("focusView", () => {
  it("scales a wide region to span about 80 % of the panel", () => {
    const view = focusView([200, 300, 900, 36], 1440, 2080, 456, 600);
    expect(view.zoom).toBeCloseTo((456 * 0.8) / 900);
    expect(200 * view.zoom - view.left).toBeCloseTo(456 * 0.1, 0);
  });

  it("fits a footer line nearly as wide as the page fully, in a tight crop", () => {
    const view = focusView([120, 2020, 1200, 14], 1440, 2080, 456, 600);
    expect(view.zoom).toBeCloseTo(456 / 1440);
    const boxLeft = 120 * view.zoom - view.left;
    const boxRight = 1320 * view.zoom - view.left;
    expect(boxLeft).toBeGreaterThanOrEqual(0);
    expect(boxRight).toBeLessThanOrEqual(456);
    // Tight: no tall empty crop around a one-line region.
    expect(view.height).toBeLessThan(250);
    const boxTop = 2020 * view.zoom - view.top;
    expect(boxTop).toBeGreaterThan(0);
    expect(boxTop + 14 * view.zoom).toBeLessThan(view.height);
  });

  it("keeps a region running past the right edge inside the frame", () => {
    const view = focusView([24, 900, 1600, 40], 1440, 2000, 520, 600);
    expect(1440 * view.zoom - view.left).toBeLessThanOrEqual(520 + 1);
    expect(24 * view.zoom - view.left).toBeGreaterThanOrEqual(0);
  });

  it("never magnifies more than the limit", () => {
    const view = focusView([300, 400, 40, 12], 1440, 2000, 520, 600, 2);
    expect(view.zoom).toBe(2);
  });

  it("shows the whole width when nothing is selected", () => {
    const view = focusView(null, 390, 3591, 456, 600);
    expect(view.zoom).toBeCloseTo(456 / 390);
    expect(view.inset).toBe(0);
    expect(view.top).toBe(0);
  });
});

describe("layoutMarkers", () => {
  const page = { x: 0, y: 0, w: 500, h: 800 };

  it("puts markers to the right of a narrow box", () => {
    const [spot] = layoutMarkers([{ x: 10, y: 100, w: 200, h: 30 }], [1], page);
    expect(spot?.x).toBeGreaterThan(210);
  });

  it("never overlaps other boxes or other marker groups", () => {
    // Stacked full-width boxes: no room left/right, little room between them.
    const boxes = [
      { x: 0, y: 100, w: 500, h: 40 },
      { x: 0, y: 150, w: 500, h: 40 },
      { x: 0, y: 200, w: 500, h: 40 },
      { x: 20, y: 60, w: 300, h: 20 },
    ];
    const spots = layoutMarkers(boxes, [2, 1, 3, 1], page);
    spots.forEach((spot, i) => {
      boxes.forEach((box) => expect(overlaps(spot, box)).toBe(false));
      spots.forEach((other, j) => {
        if (i !== j) expect(overlaps(spot, other)).toBe(false);
      });
      expect(spot.h).toBeGreaterThanOrEqual(BADGE);
    });
  });
});

function block(over: Partial<TextBlock>): TextBlock {
  return {
    text: "Zwykły tekst strony o produkcie",
    bbox: [0, 0, 600, 20],
    font_px: 16,
    font_weight: 400,
    color: "#111111",
    background: "#ffffff",
    opacity: 1,
    visible: true,
    occluded: false,
    clipped: false,
    in_footer: false,
    in_collapsed: false,
    y_ratio: 0,
    tag_path: "p",
    ...over,
  };
}

describe("textBox", () => {
  const measure = (text: string, px: number) => text.length * px * 0.5;

  it("trims a short single line in a wide container to the text", () => {
    const box = textBox([280, 640, 880, 14], "Informacje prawne", 9, measure);
    expect(box[2]).toBeLessThan(120);
    expect(box[0]).toBe(280);
  });

  it("keeps the box of multi-line text", () => {
    expect(textBox([24, 900, 342, 40], "długi tekst ".repeat(20), 9, measure)).toEqual([
      24, 900, 342, 40,
    ]);
  });
});

describe("magnifierZoom", () => {
  it("magnifies 9 px text to at least 14 px", () => {
    const zoom = magnifierZoom(9, 700, 460);
    expect(zoom * 9).toBeGreaterThanOrEqual(14);
    expect(zoom).toBeLessThanOrEqual(3);
  });

  it("magnifies short text up to 2x and never beyond the cap", () => {
    expect(magnifierZoom(12, 100, 460)).toBe(2);
    expect(magnifierZoom(3, 100, 460)).toBe(3);
  });
});

describe("blockAt and sampleBlock", () => {
  it("finds the block under the evidence", () => {
    const warning = block({ text: "Ostrzeżenie", bbox: [280, 640, 880, 14], font_px: 9 });
    expect(blockAt([block({}), warning], [280, 640, 880, 14])).toBe(warning);
  });

  it("prefers plain body copy in the main font size", () => {
    const banner = block({ background: "#1563bb", color: "#ffffff" });
    const body = block({ bbox: [0, 300, 600, 20] });
    expect(sampleBlock([banner, body, block({ font_px: 9 })], 16)).toBe(body);
    expect(isLight("rgba(0, 0, 0, 0)")).toBe(true);
    expect(isLight("rgb(21, 99, 187)")).toBe(false);
  });
});
