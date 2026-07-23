import { defineConfig, devices } from '@playwright/test';
import os from 'node:os';

/**
 * Playwright E2E test configuration for OpenConstructionERP frontend.
 *
 * Scope: this config drives the NEW QA infrastructure under `tests/e2e/`
 * (smoke/, fixtures/, helpers/). The legacy spec folder `./e2e/` is still
 * served by its dedicated configs (e.g. `playwright.boq-tour.config.ts`,
 * `playwright.match.config.ts`) and is intentionally excluded here so the
 * harness can be opted-into per-batch without sweeping in older flows.
 *
 * Run examples:
 *   npm run test:e2e:smoke           # all smoke specs, all browsers
 *   npm run test:e2e:headed          # headed (debug)
 *   npx playwright test smoke/health.spec.ts --project=chromium
 *   ./tests/e2e/runner/parallel-runner.sh batch-01-auth
 *
 * Environment variables:
 *   OE_TEST_BASE_URL    — defaults to http://localhost:5173
 *   OE_TEST_API_URL     — backend, defaults to http://localhost:8000
 *   OE_TEST_LOCALE      — en|de|ru|ar|es|fr|pt|it|pl|ja|ko|zh (default en)
 *   OE_TEST_DEMO_EMAIL  — demo account, defaults to demo@openconstructionerp.com
 *   OE_TEST_DEMO_PASSWORD
 *   OE_TEST_WORKERS     — override worker count (cap is 4)
 *   CI                  — when set, retries=2 and forbidOnly=true
 */

const BASE_URL = process.env.OE_TEST_BASE_URL ?? 'http://localhost:5173';
const LOCALE = process.env.OE_TEST_LOCALE ?? 'en';

// Workers: auto-detect cores, cap at 4 (avoids hammering the demo backend
// which rate-limits /auth/login/ at ~5 req/min per IP).
const detectedCores = Math.max(1, os.cpus()?.length ?? 1);
const defaultWorkers = Math.min(4, Math.max(1, Math.floor(detectedCores / 2)));
const workers = process.env.OE_TEST_WORKERS
  ? Number(process.env.OE_TEST_WORKERS)
  : defaultWorkers;

// Per-project URL append helper: keeps the locale query alive across navigations.
const localeUrl = (locale: string): string => {
  const u = new URL(BASE_URL);
  if (locale && locale !== 'en') u.searchParams.set('locale', locale);
  return u.toString();
};

export default defineConfig({
  testDir: './tests/e2e',
  // Only run specs under named module folders (smoke/, boq/, etc.).
  // Root-level legacy specs in tests/e2e/*.spec.ts have their own
  // dedicated configs (playwright.boq-tour.config.ts, ...) and are
  // intentionally ignored by this harness.
  testMatch: ['**/*.spec.ts'],
  testIgnore: [
    '**/fixtures/**',
    '**/helpers/**',
    '**/runner/**',
    '**/node_modules/**',
    // Legacy specs sitting directly under tests/e2e/ (one-level deep)
    // are invoked via their dedicated configs at the repo root.
    'tests/e2e/*.spec.ts',
  ],

  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers,

  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },

  reporter: [
    ['html', { outputFolder: 'qa-report', open: 'never' }],
    ['list'],
    ['json', { outputFile: 'qa-results.json' }],
  ],

  outputDir: 'test-results',

  use: {
    baseURL: localeUrl(LOCALE),
    headless: true,
    actionTimeout: 5_000,
    navigationTimeout: 30_000,
    screenshot: 'on',
    video: 'retain-on-failure',
    trace: 'on-first-retry',
    ignoreHTTPSErrors: true,
    locale: LOCALE === 'ar' ? 'ar-SA' : LOCALE,
    extraHTTPHeaders: {
      'X-DDC-Client': 'OE-QA/1.0',
    },
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    {
      // Mobile-responsive checks: iPhone SE viewport (375x667).
      name: 'mobile-chromium',
      use: {
        ...devices['iPhone SE'],
        viewport: { width: 375, height: 667 },
      },
      grep: /@mobile|@responsive/,
    },
    {
      // RTL / Arabic locale project — verifies direction handling.
      name: 'rtl-arabic',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: localeUrl('ar'),
        locale: 'ar-SA',
      },
      grep: /@rtl|@i18n/,
    },
  ],

  // We deliberately DO NOT auto-start the dev server here so test runs
  // exit cleanly with a typed error if the app is not reachable. The
  // health smoke spec surfaces a friendly "start dev server first" hint.
});
