/**
 * Standalone Playwright config for the property-dev buyer-edit E2E spec
 * (task #134). The main ``playwright.config.ts`` restricts ``testDir``
 * to ``./e2e``; the task brief explicitly requests the spec under
 * ``frontend/playwright/``, so we point a sibling config at that dir.
 */
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './playwright',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  outputDir: '.tests-artifacts/r6/property_dev/buyer_edit/_playwright',
});
