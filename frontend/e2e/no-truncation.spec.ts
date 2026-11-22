import { expect, test, type Page } from "@playwright/test";
import { anyFindingId, expectLive } from "./helpers";

/**
 * Render audit of the app's own screens: no label, name or pill is cut with an ellipsis (or a
 * line clamp), and on a phone nothing pushes the page wider than the screen. Tables may scroll
 * sideways inside their own box; toasts are transient and left out.
 */
const ROUTES = ["/sprawdz", "/zgloszenia", "/podmioty", "/monitoring", "/czulosc", "/rejestr"];
const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
];

interface Cut {
  kind: "ellipsis" | "clamp";
  className: string;
  text: string;
}

/** Elements in `main` whose text is actually cut (not just styled to be cut if too long). */
async function truncated(page: Page): Promise<Cut[]> {
  return page.evaluate(() => {
    const cuts: { kind: "ellipsis" | "clamp"; className: string; text: string }[] = [];
    for (const el of document.querySelectorAll("main *")) {
      if (!(el instanceof HTMLElement) || el.closest(".toast, details:not([open])")) continue;
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") continue;
      const text = el.innerText.trim().replace(/\s+/g, " ");
      if (!text) continue;
      const className = typeof el.className === "string" ? el.className : el.tagName;
      if (style.textOverflow === "ellipsis" && el.scrollWidth > el.clientWidth + 1)
        cuts.push({ kind: "ellipsis", className, text: text.slice(0, 80) });
      const clamp = style.getPropertyValue("-webkit-line-clamp");
      if (clamp && clamp !== "none" && el.scrollHeight > el.clientHeight + 1)
        cuts.push({ kind: "clamp", className, text: text.slice(0, 80) });
    }
    return cuts;
  });
}

/** The document is wider than the viewport (sideways page scroll on a phone). */
async function pageOverflow(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
}

for (const viewport of VIEWPORTS) {
  test.describe(`no truncated labels at ${viewport.width} px`, () => {
    test.use({ viewport });

    for (const route of ROUTES) {
      test(route, async ({ page }) => {
        await page.goto(route);
        await expect(page.locator("h1").first()).toBeVisible();
        await expectLive(page);
        await page.waitForLoadState("networkidle");
        expect(await truncated(page)).toEqual([]);
        expect(await pageOverflow(page)).toBeLessThanOrEqual(0);
      });
    }

    test("/zgloszenia/:id", async ({ page, request }) => {
      const id = await anyFindingId(request);
      await page.goto(`/zgloszenia/${id}`);
      await expect(page.getByText("Historia")).toBeVisible();
      await page.waitForLoadState("networkidle");
      expect(await truncated(page)).toEqual([]);
      expect(await pageOverflow(page)).toBeLessThanOrEqual(0);
    });
  });
}
