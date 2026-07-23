/**
 * V_DESIGN — screenshot capture for visual diff.
 *
 * Separated from the assertion spec so the screenshots are taken
 * unconditionally on every run, regardless of axe verdict.
 */
import { test, type Page } from '@playwright/test';
import * as path from 'node:path';

const DEMO_USER = {
  email: process.env.E2E_USER_EMAIL ?? 'demo@openconstructionerp.com',
};

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  const res = await page.request.post('/api/v1/users/auth/demo-login/', {
    headers: { 'Content-Type': 'application/json' },
    data: { email: DEMO_USER.email },
  });
  if (!res.ok()) throw new Error(`demo-login returned ${res.status()}`);
  const body = await res.json();
  const token = body.access_token as string | undefined;
  if (!token) throw new Error('demo-login response missing access_token');
  await page.evaluate(
    ({ tok, refresh, email }: { tok: string; refresh?: string; email: string }) => {
      sessionStorage.setItem('oe_access_token', tok);
      localStorage.setItem('oe_access_token', tok);
      if (refresh) {
        sessionStorage.setItem('oe_refresh_token', refresh);
        localStorage.setItem('oe_refresh_token', refresh);
      }
      localStorage.setItem('oe_user_email', email);
    },
    { tok: token, refresh: body.refresh_token, email: DEMO_USER.email },
  );
  await page.goto('/');
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    try {
      localStorage.setItem('oe.tour_completed', 'true');
      localStorage.setItem('oe_tour_completed', 'true');
    } catch {
      /* ignore */
    }
  });
  await login(page);
});

test('capture /dashboard screenshot', async ({ page }) => {
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(800);
  const label = process.env.SCREENSHOT_LABEL ?? 'after';
  const outPath = path.join(
    process.cwd(),
    '..',
    'qa-screenshots',
    'V_DESIGN',
    `dashboard_${label}.png`,
  );
  await page.screenshot({ path: outPath, fullPage: false });
});
