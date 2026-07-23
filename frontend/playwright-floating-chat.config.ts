/**
 * Stand-alone Playwright config for the floating-chat E2E suite.
 *
 * The repo's main `playwright.config.ts` points at port 5173 and auto-spawns
 * `npm run dev`, but our vite dev server is configured to use 5180. Rather
 * than mutate the shared config, this scoped config targets the running
 * 5180 server directly (with `reuseExistingServer: true`) and reads only
 * the floating-chat spec.
 */
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: /floating-chat\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5181',
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
});
