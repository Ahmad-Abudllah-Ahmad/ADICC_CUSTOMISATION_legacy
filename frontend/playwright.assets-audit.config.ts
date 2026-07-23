import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: /_assets-(audit|prove)\.spec\.ts/,
  fullyParallel: false,
  retries: 0,
  workers: 1,
  timeout: 240_000,
  reporter: 'line',
  use: {
    baseURL: 'http://localhost:5173',
    headless: true,
    ignoreHTTPSErrors: true,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
