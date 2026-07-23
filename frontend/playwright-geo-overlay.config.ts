/**
 * Standalone Playwright config for the geo-overlay smoke spec.
 *
 * The default config (./playwright.config.ts) auto-starts ``npm run dev``
 * targeting port 5173 — but this monorepo's vite uses port 5180 and
 * frequently has an existing dev server already running. We bypass the
 * webServer block entirely and assume the caller has started vite +
 * backend already (``npm run dev`` in frontend/, plus
 * ``uvicorn app.main:create_app --factory --port 8000`` in backend/).
 */
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'geo-overlay.spec.ts',
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.E2E_FRONTEND_BASE ?? 'http://localhost:5181',
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
