/**
 * Standalone Playwright config for the BOQ Editor tour spec.
 *
 * Why a separate file: the default `playwright.config.ts` declares a
 * `webServer` that wants port 5173 and runs a `globalSetup` script that
 * isn't present in this worktree. The BOQ tour spec assumes a Vite
 * dev server is already running on port 5180 and a backend on 9090 —
 * we point this config at the live processes rather than start fresh
 * ones.
 *
 * Run:
 *   npx playwright test --config=playwright.boq-tour.config.ts \
 *     tests/e2e/boq-tour.spec.ts
 */
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:5180',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    ignoreHTTPSErrors: true,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
