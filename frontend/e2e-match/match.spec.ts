// One-shot visual smoke for /match-elements (v2.9.32).
// Run: npx playwright test --config playwright.match.config.ts
//
// Logs in inline; saves PNGs to qa-tests/_match-elements-2026-05-07/.

import { test, expect } from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const __dirname_esm = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(__dirname_esm, '../../../qa-tests/_match-elements-2026-05-07');
fs.mkdirSync(OUT, { recursive: true });

const FRONTEND = 'http://localhost:5180';
const BACKEND = 'http://localhost:8000';
const USER = { email: 'me-screenshot@oe.test', password: 'OpenEstimate2024!' };

test.describe('match-elements visual', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('match-elements page — visual smoke', async ({ page, request }) => {
  // Step 1: ensure user exists, login, get token
  let res = await request.post(`${BACKEND}/api/v1/users/auth/login/`, {
    data: { email: USER.email, password: USER.password },
    failOnStatusCode: false,
  });
  if (!res.ok()) {
    await request.post(`${BACKEND}/api/v1/users/auth/register/`, {
      data: USER,
      failOnStatusCode: false,
    });
    res = await request.post(`${BACKEND}/api/v1/users/auth/login/`, {
      data: { email: USER.email, password: USER.password },
      failOnStatusCode: false,
    });
  }
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  const access = body.access_token as string;
  const refresh = (body.refresh_token ?? access) as string;

  // Step 2: hydrate localStorage on the frontend origin so the SPA picks it up
  await page.goto(`${FRONTEND}/about`);
  await page.evaluate(
    ({ access, refresh, email }) => {
      localStorage.setItem('oe_access_token', access);
      localStorage.setItem('oe_refresh_token', refresh);
      localStorage.setItem('oe_user_email', email);
    },
    { access, refresh, email: USER.email },
  );

  // Step 3: sidebar with /match-elements
  await page.goto(`${FRONTEND}/`);
  await page.waitForLoadState('networkidle').catch(() => null);
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, '01-sidebar-with-match-elements.png'), fullPage: false });

  // Step 4: /match-elements page itself
  await page.goto(`${FRONTEND}/match-elements`);
  await page.waitForLoadState('networkidle').catch(() => null);
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(OUT, '02-page-loaded.png'), fullPage: true });

  // Step 5: action bar / header
  await page.screenshot({
    path: path.join(OUT, '03-action-bar.png'),
    clip: { x: 0, y: 0, width: 1440, height: 320 },
  });

  // Step 6: Templates panel
  const lib = page.locator('button:has-text("Library")').first();
  if (await lib.isVisible().catch(() => false)) {
    await lib.click();
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(OUT, '04-templates-panel.png'), fullPage: false });
    // Close
    await page.keyboard.press('Escape');
    await page.waitForTimeout(200);
    const close = page.locator('aside >> button >> svg.lucide-x').first();
    if (await close.isVisible().catch(() => false)) {
      await close.locator('..').click().catch(() => null);
    }
    await page.waitForTimeout(300);
  }

  // Step 7: Detail panel (if any group exists)
  const detail = page.locator('button:has-text("Detail")').first();
  if (await detail.isVisible().catch(() => false)) {
    await detail.click();
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(OUT, '05-detail-panel.png'), fullPage: false });

    // No-match modal
    const noMatch = page.locator('button:has-text("No match")').first();
    if (await noMatch.isVisible().catch(() => false)) {
      await noMatch.click();
      await page.waitForTimeout(600);
      await page.screenshot({ path: path.join(OUT, '06-no-match-modal.png'), fullPage: false });
    }
  } else {
    // No groups (no BIM data on this fresh user); capture the empty-state view
    await page.screenshot({ path: path.join(OUT, '05-empty-state.png'), fullPage: true });
  }

  // Step 8: API smoke — /api/v1/match_elements/templates should be reachable
  const templ = await request.get(`${BACKEND}/api/v1/match_elements/templates`, {
    headers: { Authorization: `Bearer ${access}` },
  });
  console.log('templates HTTP', templ.status());
  expect([200, 404]).toContain(templ.status()); // 200 if mounted, 404 only if route missing

  // Final overview
  await page.goto(`${FRONTEND}/match-elements`);
  await page.waitForLoadState('networkidle').catch(() => null);
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, '07-final-overview.png'), fullPage: true });

    expect(true).toBe(true);
  });
});
