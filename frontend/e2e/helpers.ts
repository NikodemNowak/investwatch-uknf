import { execSync } from "node:child_process";
import { expect, type APIRequestContext, type ConsoleMessage, type Page } from "@playwright/test";

/** Collect every console message and uncaught page error of a page. */
export function watchConsole(page: Page): string[] {
  const seen: string[] = [];
  page.on("console", (msg: ConsoleMessage) => seen.push(`[${msg.type()}] ${msg.text()}`));
  page.on("pageerror", (err) => seen.push(`[pageerror] ${err.message}`));
  return seen;
}

/** The "Na żywo" indicator in the top bar. */
export const liveIndicator = (page: Page) => page.locator(".live");

/** Wait until the Socket.IO channel is connected. */
export async function expectLive(page: Page): Promise<void> {
  await expect(liveIndicator(page)).toHaveText("Na żywo", { timeout: 30_000 });
}

interface CheckJob {
  job_id: string;
  state?: string;
  finding_ids?: string[];
}

/**
 * Submit material that the rules (and the mock analyzer) rate as high risk; returns the finding
 * ids once the job is done. A nonce keeps it from being a duplicate of an earlier run.
 */
export async function submitHighRisk(request: APIRequestContext, nonce: string): Promise<string[]> {
  const text =
    `Fundusz Turbo Zysk ${nonce}: gwarantowany zysk 40% rocznie, w ostatnich 12 miesiącach ` +
    "średnia stopa zwrotu 38%! Zarabiaj miesięcznie bez wysiłku. Dołącz dziś, liczba miejsc " +
    "ograniczona. Kupuj teraz, zanim kurs wzrośnie.";
  const started = await request.post("/api/check", { data: { text } });
  expect(started.ok()).toBeTruthy();
  const job = (await started.json()) as CheckJob;
  let ids: string[] = [];
  await expect
    .poll(
      async () => {
        const state = (await (await request.get(`/api/check/${job.job_id}`)).json()) as CheckJob;
        ids = state.finding_ids ?? [];
        return state.state;
      },
      { timeout: 45_000 },
    )
    .toBe("done");
  return ids;
}

/** Id of any finding; creates one through the pipeline when the database has none. */
export async function anyFindingId(request: APIRequestContext): Promise<string> {
  const page = (await (await request.get("/api/findings?page_size=1")).json()) as {
    items: { id: string }[];
  };
  const first = page.items[0];
  if (first) return first.id;
  const ids = await submitHighRisk(request, `seed-${Date.now()}`);
  expect(ids.length).toBeGreaterThan(0);
  return ids[0] as string;
}

/** Restart the API with `E2E_RESTART_API` (e.g. `docker compose restart api`). */
export function restartApi(): void {
  const cmd = process.env.E2E_RESTART_API;
  if (!cmd) throw new Error("E2E_RESTART_API is not set");
  execSync(cmd, { stdio: "inherit", timeout: 120_000 });
}
