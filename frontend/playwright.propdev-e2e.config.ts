/**
 * Playwright config — comprehensive property_dev R6 E2E suite (task #143).
 *
 * Covers the full buyer journey end-to-end:
 *   Lead → Reservation → SPA (multi-buyer) → PaymentSchedule + Instalments →
 *   Handover → Snags → WarrantyClaim, plus Broker / Commission / Escrow /
 *   PriceMatrix / Phase / Block hierarchy and regulator reports.
 *
 * Why a separate config rather than dropping the specs into ../e2e?
 *   - The buyer-journey scenarios mutate large amounts of state across
 *     ~190 endpoints; running them in parallel with the default e2e
 *     suite would race on the shared sqlite dev DB.
 *   - We need workers=1 to avoid SPA fixture / tenant collisions while
 *     still allowing scenarios to be assigned to different ports for
 *     local manual debugging.
 *   - The artifact + trace output is namespaced under
 *     ``.tests-artifacts/r6/property_dev/`` so the runner can collect
 *     them without scraping the rest of the e2e output.
 *
 * Run all:    npx playwright test -c playwright.propdev-e2e.config.ts
 * Single:     npx playwright test -c playwright.propdev-e2e.config.ts e2e/propdev/01-happy-path.spec.ts
 *
 * Backend + frontend dev servers must be running on the standard ports
 * (8000 / 5173) before invocation. The config does NOT auto-spawn them
 * to keep the spec self-contained — each scenario seeds + tears down
 * its own state via direct API calls against the running backend.
 */
import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname_esm = path.dirname(fileURLToPath(import.meta.url));
const ARTIFACT_ROOT = path.resolve(
  __dirname_esm,
  '..',
  '.tests-artifacts',
  'r6',
  'property_dev',
);

export default defineConfig({
  testDir: './e2e/propdev',
  // Serial execution — every scenario seeds its own dev / phase / block /
  // plot graph and asserts cross-tenant isolation. Parallel runs would
  // step on the same buyer rows in the shared sqlite dev DB.
  fullyParallel: false,
  workers: 1,
  // Allow one retry locally so flaky LLM-judge / OCR steps don't
  // permanently red the report; CI gets no retries to keep regressions
  // visible.
  retries: process.env.CI ? 0 : 1,
  forbidOnly: !!process.env.CI,
  // Generous timeout — the happy-path spec makes ~80 API calls and
  // captures 30+ screenshots in a single test fn.
  timeout: 240_000,
  expect: { timeout: 15_000 },
  reporter: [
    ['list'],
    ['html', { outputFolder: path.join(ARTIFACT_ROOT, 'html-report'), open: 'never' }],
    ['json', { outputFile: path.join(ARTIFACT_ROOT, 'results.json') }],
  ],
  outputDir: path.join(ARTIFACT_ROOT, 'test-output'),
  use: {
    baseURL: process.env.PROPDEV_BASE_URL ?? 'http://localhost:5173',
    headless: true,
    // We capture screenshots manually at every step; let Playwright
    // grab failure snapshots as a belt-and-braces fallback.
    screenshot: 'only-on-failure',
    // Trace every run — we want a trace.zip for both pass and fail so
    // the runner can dig into role-gate flakiness.
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    ignoreHTTPSErrors: true,
    actionTimeout: 30_000,
    navigationTimeout: 45_000,
  },
  projects: [
    {
      name: 'chromium-propdev',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
