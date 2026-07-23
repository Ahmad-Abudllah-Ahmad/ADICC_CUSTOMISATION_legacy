/**
 * Dedicated Playwright config for the wave-2 dashboard widgets E2E.
 *
 * Used because:
 *   - The main playwright.config.ts hardcodes baseURL=5173 and tries to
 *     auto-start ``npm run dev`` on 5180 (which is already taken by the
 *     main worktree's Vite). This config skips the webServer block and
 *     points at the worktree-local Vite on 5290 started manually by the
 *     verification step.
 *   - We don't want to mutate the shared config (the spec says
 *     "Don't touch other features' files").
 *
 * Run:
 *   npx playwright test e2e/dashboard-widgets.spec.ts \
 *     --config playwright.dashboard-widgets.config.ts
 */
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'dashboard-widgets.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:5290',
    headless: true,
    screenshot: 'only-on-failure',
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
