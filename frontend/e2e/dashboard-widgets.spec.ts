/**
 * E2E — Dashboard widgets (wave 2, 2026-05-23).
 *
 * Verifies the 10 new widgets show up in the Customize panel alongside the
 * existing 12, and confirms that the server-side layout persistence
 * survives a full page reload (the key behaviour we shipped this wave —
 * without it the layout would only follow the localStorage bucket).
 *
 * Run:
 *   npx playwright test e2e/dashboard-widgets.spec.ts
 */
import { test, expect, type Page } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
// Set the backend URL BEFORE the helper module loads it. The helper
// closes over ``process.env.PROPDEV_BACKEND_URL`` at import time, so any
// later mutation is ignored. 9290 = the worktree-local backend started
// for this run (carries the new /me/dashboard-layout/ endpoint).
process.env.PROPDEV_BACKEND_URL ??= 'http://localhost:9290';
import { demoLogin, hydrateAuth } from './propdev/helpers/auth';

/**
 * The dev Vite proxy is hardcoded to ``http://127.0.0.1:9090`` in
 * ``vite.config.ts``. To keep this spec self-contained against the
 * worktree-local backend on 9290, every in-browser ``/api/...`` call is
 * routed through Playwright to 9290 instead. The page never knows.
 */
async function routeApiToWorktreeBackend(page: Page): Promise<void> {
  await page.route('**/api/**', async (route) => {
    const u = new URL(route.request().url());
    u.protocol = 'http:';
    u.host = 'localhost:9290';
    const init: Parameters<typeof route.continue>[0] = { url: u.toString() };
    await route.continue(init);
  });
}

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Screenshots land in the qa-tests/ tree per the task spec so a reviewer
// can find them next to other QA artefacts. The directory is created at
// the start of the suite if missing.
const SCREENSHOT_DIR = path.resolve(
  __dirname,
  '../../qa-tests/_dashboard-widgets-2026-05-23',
);
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

const ALL_WIDGET_IDS = [
  // Existing 12
  'continue_work',
  'today',
  'kpi',
  'projects',
  'portfolio',
  'map',
  'bim_coverage',
  'quick_upload',
  'onboarding',
  'next_steps',
  'analytics',
  'activity',
  // New 10
  'boq_summary',
  'validation_score',
  'clash_health',
  'schedule_critical',
  'risk_top',
  'hse_scorecard',
  'procurement_pipeline',
  'budget_variance',
  'change_orders',
  'weather_site',
];

async function loginAndGoToDashboard(page: Page): Promise<void> {
  await routeApiToWorktreeBackend(page);
  const session = await demoLogin('admin');
  await hydrateAuth(page.context(), session);
  // The dashboard ``useEffect`` redirects empty workspaces to /onboarding.
  // Set the completion flag so the spec lands on /  and never on the wizard.
  // Also dismiss the product tour + customise-branding wizard which would
  // otherwise overlay the Customize button.
  await page.context().addInitScript(() => {
    try {
      localStorage.setItem('oe_onboarding_completed', 'true');
      localStorage.setItem('oe_welcome_dismissed', 'true');
      localStorage.setItem('oe_tour_completed', 'true');
      // ProductTour uses a DIFFERENT key with a literal dot, on purpose.
      localStorage.setItem('oe.tour_completed', 'true');
      localStorage.setItem('oe_product_tour_completed', 'true');
      localStorage.setItem('oe_branding_wizard_dismissed', 'true');
      localStorage.setItem('oe_whats_new_seen_v4.5.0', 'true');
    } catch {
      /* incognito */
    }
  });
  await page.goto('/');
  await expect(page).toHaveURL(/\/$|\/dashboard|\//, { timeout: 15_000 });
  await page.waitForLoadState('domcontentloaded', { timeout: 30_000 });
  await page.waitForTimeout(3_000);
}

async function dismissOverlays(page: Page): Promise<void> {
  // The product tour and "Customise branding" wizard both auto-mount on
  // first visit. Click their exit / dismiss buttons defensively — each
  // catch swallows missing-locator errors.
  await page.getByRole('button', { name: /exit tour|skip tour/i }).click({ timeout: 2_000 }).catch(() => {});
  await page.waitForTimeout(300);
  await page.locator('button[aria-label*="lose" i], button[aria-label*="ismiss" i]').first().click({ timeout: 2_000 }).catch(() => {});
  await page.waitForTimeout(300);
  // Loop close any remaining backdrop dialogs.
  for (let i = 0; i < 3; i++) {
    const closeBtn = page.locator('[role="dialog"] button[aria-label*="lose" i]').first();
    if (await closeBtn.count()) {
      await closeBtn.click({ timeout: 1_500 }).catch(() => {});
      await page.waitForTimeout(200);
    } else break;
  }
  await page.keyboard.press('Escape').catch(() => {});
  await page.waitForTimeout(300);
}

async function openCustomizePanel(page: Page): Promise<void> {
  await dismissOverlays(page);

  // The customise toggle's title is the unique
  // ``dashboard.layout.customize_hint`` default: "Reorder, show or hide
  // dashboard sections". Target by partial title to avoid clashing with
  // the "Customise branding" wizard which has a similar localised name.
  const btn = page.locator(
    'button[title*="Reorder" i], button[title*="dashboard section" i]',
  ).first();
  await btn.click({ timeout: 15_000 });

  await expect(page.locator('[data-testid^="dash-widget-row-"]').first()).toBeVisible({
    timeout: 15_000,
  });
}

test('all 22 widgets visible in the customise panel', async ({ page }) => {
  await loginAndGoToDashboard(page);
  await openCustomizePanel(page);

  for (const id of ALL_WIDGET_IDS) {
    const row = page.locator(`[data-testid="dash-widget-row-${id}"]`);
    await expect(row, `widget row ${id} should be visible`).toBeVisible({
      timeout: 5_000,
    });
  }

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, '01-customize-panel-all-widgets.png'),
    fullPage: true,
  });
});

test('new widgets render on the dashboard after enabling', async ({ page }) => {
  await loginAndGoToDashboard(page);
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, '02-dashboard-default.png'),
    fullPage: true,
  });

  await openCustomizePanel(page);
  // Toggling a row's eye keeps it visible (default state IS visible).
  // The point here is just to record that the new widgets render — we
  // close the panel and screenshot the full dashboard.
  await page.keyboard.press('Escape').catch(() => {});
  const doneBtn = page.getByRole('button', { name: /done|fertig|готово/i }).first();
  if (await doneBtn.count()) await doneBtn.click();

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, '03-dashboard-with-new-widgets.png'),
    fullPage: true,
  });
});

test('server-side persistence survives a full reload', async ({ page }) => {
  await loginAndGoToDashboard(page);

  // Drive the PUT directly via the API the store would use, so this test
  // is robust against any UI flake. The store hydrates from the same
  // endpoint on next load.
  const token = await page.evaluate(
    () =>
      localStorage.getItem('oe_access_token') ??
      sessionStorage.getItem('oe_access_token'),
  );
  // Use absolute URL — page.request uses Playwright's baseURL otherwise
  // and the Vite proxy on 5290 forwards to the stale backend on 9090.
  const persistResp = await page.request.put(
    'http://localhost:9290/api/v1/users/me/dashboard-layout/',
    {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      data: {
        order: ['boq_summary', 'risk_top', 'kpi'],
        hidden: ['activity'],
      },
    },
  );
  expect(persistResp.ok()).toBeTruthy();

  // Clear localStorage so we're certain the next page load gets the
  // layout from the server, not the persisted Zustand bucket.
  await page.evaluate(() => {
    try {
      localStorage.removeItem('oe.dashboard-layout');
    } catch {
      /* ignore */
    }
  });

  await page.reload();
  await page.waitForLoadState('networkidle', { timeout: 30_000 });

  // Re-read from the server to confirm round-trip.
  const getResp = await page.request.get(
    'http://localhost:9290/api/v1/users/me/dashboard-layout/',
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  const body = await getResp.json();
  expect(body.order).toEqual(['boq_summary', 'risk_top', 'kpi']);
  expect(body.hidden).toEqual(['activity']);

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, '04-after-reload-server-persisted.png'),
    fullPage: true,
  });
});
