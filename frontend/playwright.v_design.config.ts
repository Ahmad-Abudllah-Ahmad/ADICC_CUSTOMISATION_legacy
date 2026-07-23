/**
 * Standalone Playwright config for V_DESIGN a11y spec.
 *
 * Lets us run `qa/V_DESIGN.spec.ts` without disturbing the main
 * `playwright.config.ts` test-discovery rules (it only sees
 * `tests/e2e/<suite>/*.spec.ts`).
 */
import { defineConfig, devices } from '@playwright/test';

const BASE_URL = process.env.OE_TEST_BASE_URL ?? 'http://127.0.0.1:5191';

export default defineConfig({
  testDir: './e2e',
  testMatch: ['V_DESIGN.spec.ts', 'V_DESIGN_screenshots.spec.ts'],
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  outputDir: 'test-results-v-design',
  use: {
    baseURL: BASE_URL,
    headless: true,
    screenshot: 'only-on-failure',
    actionTimeout: 5_000,
    navigationTimeout: 30_000,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
