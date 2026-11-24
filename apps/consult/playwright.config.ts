import { defineConfig, devices } from "@playwright/test";

// Its own port, so a `pnpm dev` already running on 3006 is left alone and the
// flow always starts from a fresh fixture.
const PORT = Number(process.env.CONSULT_E2E_PORT ?? 3016);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  // `next dev` compiles each route on first visit, so allow for that.
  timeout: 120_000,
  expect: { timeout: 30_000 },
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    // Containers without a user namespace need these; harmless elsewhere.
    launchOptions: { args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"] },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `pnpm exec next dev --port ${PORT} --hostname 127.0.0.1`,
    url: `http://127.0.0.1:${PORT}/healthz`,
    reuseExistingServer: false,
    timeout: 120_000,
    // The flow runs against the in-memory fixture, never a real Odoo.
    env: { CONSULT_FIXTURE: "1", CONSULT_AUTH_BYPASS: "1", NEXT_TELEMETRY_DISABLED: "1", CI: "1" },
  },
});
