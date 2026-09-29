import { existsSync } from "node:fs";

import { defineConfig, devices } from "@playwright/test";

// The exported site, served the way GitHub Pages serves it: under the base path, with byte ranges.
// Build once with `npm run build`; the tests never rebuild.
const PORT = Number(process.env.LOOKAHEAD_E2E_PORT ?? 4173);
const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "/lookahead";
// This sandbox ships a Chromium outside Playwright's cache; CI installs its own and skips this.
const chromium = process.env.LOOKAHEAD_CHROMIUM ?? "/opt/pw-browsers/chromium";

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  expect: { timeout: 20_000 },
  fullyParallel: true,
  workers: 2,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    ...(existsSync(chromium) ? { launchOptions: { executablePath: chromium } } : {}),
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1360, height: 900 } }, testIgnore: /layout\.spec\.ts/ },
    { name: "phone", use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } }, testMatch: /layout\.spec\.ts/ },
  ],
  webServer: {
    command: "node scripts/serve.mjs",
    url: `http://127.0.0.1:${PORT}${BASE}/`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
