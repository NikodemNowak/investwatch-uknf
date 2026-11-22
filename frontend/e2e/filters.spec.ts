import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/** Submit high-risk material "seen" on `host`; resolves once its findings exist. */
async function submitFromSite(request: APIRequestContext, host: string): Promise<void> {
  const text =
    `Fundusz Turbo Zysk (${host}): gwarantowany zysk 40% rocznie, w ostatnich 12 miesiącach ` +
    "średnia stopa zwrotu 38%! Kupuj teraz akcje, które Ci wskażę, zanim kurs wzrośnie. " +
    "Indywidualne rekomendacje dla Ciebie, zarządzamy Twoimi pieniędzmi.";
  const created = await request.post("/api/submissions", {
    multipart: { text, url: `https://${host}/oferta` },
  });
  expect(created.ok()).toBeTruthy();
  await expect
    .poll(
      async () => {
        const page = (await (
          await request.get(`/api/findings?q=${encodeURIComponent(host)}`)
        ).json()) as { total: number };
        return page.total;
      },
      { timeout: 45_000 },
    )
    .toBeGreaterThan(0);
}

/** Pick one option of a single-choice filter (period, risk, status). */
const choose = async (page: Page, filter: string, option: RegExp) => {
  await page.getByTestId(`filter-${filter}`).click();
  await page.getByRole("menuitemradio", { name: option }).click();
};

test.describe("result filters, status from the list and the aggregator", () => {
  const host = `turbo-zysk-${Date.now()}.example`;

  test.beforeAll(async ({ request }) => {
    await submitFromSite(request, host);
  });

  test("filters by source and status, synced with the URL, and clears", async ({ page }) => {
    await page.goto("/zgloszenia");
    await expect(page.getByTestId("review-row").first()).toBeVisible();

    await page.getByTestId("filter-source").click();
    await page.getByRole("menuitemcheckbox", { name: "Strona WWW" }).click();
    await page.keyboard.press("Escape");
    await expect(page).toHaveURL(/zrodlo=web/);
    const rows = page.getByTestId("review-row");
    await expect(rows.first()).toBeVisible();
    for (const text of await rows.allInnerTexts()) expect(text).toContain("Strona WWW");

    await choose(page, "period", /Ostatnie 7 dni/);
    await expect(page).toHaveURL(/okres=7-dni/);
    await choose(page, "status", /^Potwierdzone/);
    await expect(page).toHaveURL(/status=potwierdzone/);

    await page.getByRole("button", { name: "Wyczyść filtry" }).click();
    await expect(page).not.toHaveURL(/zrodlo|okres|status=/);
    await expect(page.getByRole("button", { name: "Wyczyść filtry" })).toBeDisabled();
  });

  test("changes the status from the list row menu", async ({ page }) => {
    await page.goto(`/zgloszenia?status=wszystkie&q=${host}`);
    const row = page.getByTestId("review-row").first();
    await expect(row).toContainText(host);
    await row.getByTestId("row-status-menu").click();
    await page.getByRole("menuitemradio", { name: "Potwierdź naruszenie" }).click();
    await expect(page.locator(".toast").first()).toContainText("Potwierdzone naruszenie");
    await expect(row.getByTestId("status-tag")).toHaveText("Potwierdzone");

    await choose(page, "status", /^Odrzucone/);
    await expect(page.getByText("Brak materiałów dla wybranych filtrów.")).toBeVisible();
    await choose(page, "status", /^Potwierdzone/);
    await expect(page.getByTestId("review-row").first()).toContainText(host);
  });

  test("aggregates the entity and drills down to its findings", async ({ page }) => {
    await page.goto(`/podmioty?status=wszystkie&q=${host}`);
    await expect(page.locator("h1")).toHaveText("Agregator wyników");
    const row = page.getByTestId("entity-row").first();
    await expect(row).toContainText(host);
    await expect(row.getByTestId("register-tag")).toHaveText("Brak w rejestrze KNF");
    await row.getByRole("link", { name: host }).click();

    await expect(page.locator("h1")).toHaveText(host);
    const timeline = page.getByTestId("timeline-row");
    await expect(timeline.first()).toBeVisible();
    await timeline.first().locator(".row-link").click();
    await expect(page).toHaveURL(/\/zgloszenia\/[0-9a-f-]{36}$/);
  });
});
