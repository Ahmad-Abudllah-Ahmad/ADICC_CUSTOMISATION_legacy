/**
 * Temporary Playwright config for the floating-chat-onboarding spec.
 * Reuses the existing dev server on port 5188 (spun up manually by the
 * worktree agent) instead of trying to spawn a new one — strictPort:true
 * in vite.config.ts would otherwise collide with the parallel worktree
 * Vite instances already bound to 5180.
 */
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'floating-chat-onboarding.spec.ts',
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5188',
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
