import { expect, test } from "@playwright/test";
import { anyFindingId, expectLive, watchConsole } from "./helpers";

const ROUTES: { path: string; ready: RegExp }[] = [
  { path: "/sprawdz", ready: /Sprawdź/ },
  { path: "/zgloszenia", ready: /Do przejrzenia/ },
  { path: "/podmioty", ready: /Agregator wyników/ },
  { path: "/monitoring", ready: /Monitoring/ },
  { path: "/czulosc", ready: /Czułość/ },
  { path: "/rejestr", ready: /Rejestr/ },
];

test.describe("production build: no console messages", () => {
  for (const route of ROUTES) {
    test(route.path, async ({ page }) => {
      const messages = watchConsole(page);
      await page.goto(route.path);
      await expect(page.locator("h1").first()).toHaveText(route.ready);
      await expectLive(page);
      await page.waitForLoadState("networkidle");
      expect(messages).toEqual([]);
    });
  }

  test("/zgloszenia/:id", async ({ page, request }) => {
    const id = await anyFindingId(request);
    const messages = watchConsole(page);
    await page.goto(`/zgloszenia/${id}`);
    await expect(page.locator("h1").first()).not.toBeEmpty();
    await expect(page.getByText("Historia")).toBeVisible();
    await expectLive(page);
    await page.waitForLoadState("networkidle");
    expect(messages).toEqual([]);
  });
});
