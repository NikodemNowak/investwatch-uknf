import { expect, test } from "@playwright/test";

test("a social-media URL leads to the 'Zgłoś materiał' form, in plain Polish", async ({ page }) => {
  await page.goto("/sprawdz");
  await page.locator("#url").fill("https://www.facebook.com/zlotyzysk/posts/1");
  await page.getByRole("button", { name: "Sprawdź", exact: true }).click();

  const refusal = page.getByRole("alert");
  await expect(refusal).toContainText("Tej strony nie pobieramy automatycznie");
  await expect(refusal).not.toContainText("/api/");

  await refusal.getByRole("button", { name: "Zgłoś materiał" }).click();
  const dialog = page.getByRole("dialog", { name: "Zgłoś materiał" });
  await expect(dialog.getByLabel("Adres materiału (opcjonalnie)")).toHaveValue(
    "https://www.facebook.com/zlotyzysk/posts/1",
  );
  await dialog
    .getByLabel("Treść posta lub reklamy")
    .fill(`Gwarantowany zysk 30% miesięcznie, bez ryzyka. ${Date.now()}`);
  await dialog.getByRole("button", { name: "Zgłoś do analizy" }).click();

  await expect(page.locator(".toast--success")).toContainText("Przyjęto materiał");
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("alert")).toHaveCount(0);
});
