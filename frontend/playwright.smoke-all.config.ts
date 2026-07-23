import { defineConfig, devices } from '@playwright/test';

/**
 * Smoke-all-modules across 3 desktop engines against the single-server build
 * on :8000. Captures per-route screenshots + findings JSON under qa-smoke/.
 * The app must already be running (no webServer auto-start).
 */
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: ['smoke-all-modules.spec.ts'],
  fullyParallel: false,
  workers: Number(process.env.OE_SMOKE_WORKERS ?? 3),
  retries: 0,
  timeout: 75_000,
  reporter: [
    ['list'],
    ['json', { outputFile: 'qa-smoke/results.json' }],
    ['html', { outputFolder: 'qa-smoke-report', open: 'never' }],
  ],
  outputDir: 'qa-smoke/test-results',
  use: {
    baseURL: process.env.OE_TEST_BASE_URL ?? 'http://127.0.0.1:8000',
    screenshot: 'off',
    video: 'off',
    trace: 'retain-on-failure',
    ignoreHTTPSErrors: true,
    navigationTimeout: 30_000,
    actionTimeout: 15_000,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
});
