/**
 * Clean E2E config for the comprehensive full-app smoke against the live
 * single-server build. Unlike playwright.config.ts this does NOT inject the
 * X-DDC-Client header globally — that header makes maplibre/Cesium fetches
 * "non-simple", triggering CORS preflights that the basemap/font CDNs reject,
 * which shows up as false-positive console errors. A real browser never adds
 * that header to third-party or basemap requests.
 */
import { defineConfig, devices } from '@playwright/test';

const BASE_URL = process.env.OE_TEST_BASE_URL ?? 'http://localhost:8000';

export default defineConfig({
  testDir: './tests/e2e/comprehensive',
  testMatch: ['**/*.spec.ts'],
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 600_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  outputDir: 'test-results-e2e-clean',
  use: {
    baseURL: BASE_URL,
    headless: true,
    actionTimeout: 8_000,
    navigationTimeout: 30_000,
    screenshot: 'on',
    video: 'off',
    trace: 'off',
    ignoreHTTPSErrors: true,
    // NB: no extraHTTPHeaders here.
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
