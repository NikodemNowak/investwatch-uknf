import { defineConfig, devices } from "@playwright/test";

/**
 * Browser tests of the production build (`frontend/e2e/`).
 *
 * `E2E_BASE_URL` points at a running UI with its API behind it:
 * - CI / `make e2e-light`: `vite preview` of `dist/` + the API on SQLite, Redis, mock AI
 *   (`e2e/light-stack.sh`);
 * - `make e2e`: the full Compose stack at http://localhost:8080.
 * `E2E_RESTART_API` is the shell command that restarts the API (reconnect test).
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:4173",
    trace: "retain-on-failure",
    viewport: { width: 1440, height: 900 },
    locale: "pl-PL",
    timezoneId: "Europe/Warsaw",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
});
