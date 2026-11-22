import { expect, test } from "@playwright/test";
import { submitHighRisk } from "./helpers";

test("finding: PDF link and the 'Pod maską' trace", async ({ page, request }) => {
  const [id] = await submitHighRisk(request, `hood-${Date.now()}`);
  expect(id).toBeTruthy();
  await page.goto(`/zgloszenia/${id}`);
  const pdf = page.getByRole("link", { name: "Pobierz raport PDF" });
  await expect(pdf).toHaveAttribute("href", `/api/findings/${id}/report.pdf`);

  const hood = page.locator("#pod-maska");
  await expect(hood.locator("summary")).toContainText("Źródło:");
  await hood.locator("summary").click();
  await expect(hood.getByText("Kopia dowodowa (MinIO)")).toBeVisible();
  await expect(hood.getByText("SHA-256 tekstu")).toBeVisible();
  await expect(hood.getByText("Czas kroków")).toBeVisible();

  const trace = await (await request.get(`/api/findings/${id}/trace`)).json();
  expect(trace.content_hash).toMatch(/^[0-9a-f]{64}$/);
});

test("monitoring: system status card", async ({ page }) => {
  await page.goto("/monitoring");
  const card = page.locator(".system");
  await expect(card.getByText("Stan systemu")).toBeVisible();
  await expect(card.getByText("Baza danych")).toBeVisible();
  await expect(card.locator(".system__service")).toHaveCount(8);
});

test("sensitivity: chart follows the slider", async ({ page }) => {
  await page.goto("/czulosc");
  await expect(page.locator("h1")).toHaveText(/Czułość/);
  // The chart is lazy-loaded; without labels the page shows an empty state instead.
  const chart = page.locator(".calib-chart:not(.calib-chart--loading)");
  await chart.or(page.locator(".state")).first().waitFor();
  test.skip((await chart.count()) === 0, "no labelled outcomes in this database");
  await page.locator("#thr").fill("30");
  await expect(chart.getByText("próg 0,30")).toBeVisible();
  await page.locator("#thr").fill("80");
  await expect(chart.getByText("próg 0,80")).toBeVisible();
});
