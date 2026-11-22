import { expect, test } from "@playwright/test";
import { expectLive, liveIndicator, restartApi, submitHighRisk } from "./helpers";

test("a high-risk alert from the API shows up in an open tab without a reload", async ({
  page,
  request,
}) => {
  await page.goto("/zgloszenia");
  await expectLive(page);
  let navigations = 0;
  page.on("framenavigated", (frame) => {
    if (frame === page.mainFrame()) navigations += 1;
  });

  const ids = await submitHighRisk(request, `alert-${Date.now()}`);
  expect(ids.length).toBeGreaterThan(0);

  const toast = page.locator(".toast--danger").first();
  await expect(toast).toContainText("Wysokie ryzyko");
  const open = toast.getByRole("link", { name: "Otwórz" });
  await expect(open).toHaveAttribute("href", new RegExp(`/zgloszenia/(${ids.join("|")})$`));
  expect(navigations).toBe(0);
});

test("the tab reconnects after the API restarts", async ({ page, request }) => {
  test.skip(!process.env.E2E_RESTART_API, "set E2E_RESTART_API to the restart command");
  test.setTimeout(180_000);
  await page.goto("/zgloszenia");
  await expectLive(page);
  // Remember whether the tab ever showed "Brak połączenia" (it may flip back quickly).
  await page.evaluate(() => {
    const flags = window as unknown as { sawOffline?: boolean };
    flags.sawOffline = false;
    const live = document.querySelector(".live");
    if (!live) return;
    new MutationObserver(() => {
      if (live.textContent?.includes("Brak połączenia")) flags.sawOffline = true;
    }).observe(live, { subtree: true, childList: true, characterData: true });
  });

  restartApi();
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { sawOffline?: boolean }).sawOffline), {
      timeout: 30_000,
    })
    .toBe(true);
  await expect(liveIndicator(page)).toHaveText("Na żywo", { timeout: 90_000 });

  // The new connection carries alerts again.
  await submitHighRisk(request, `reconnect-${Date.now()}`);
  await expect(page.locator(".toast--danger").first()).toContainText("Wysokie ryzyko", {
    timeout: 30_000,
  });
});
