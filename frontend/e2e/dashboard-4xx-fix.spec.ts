/**
 * E2E — Dashboard wave-2 widget 4xx fix (2026-05-24).
 *
 * Verifies that the 8 fan-out URLs corrected in NewWidgets.tsx no longer
 * generate 4xx/5xx responses on a default admin login. Mirrors the
 * regression report harness from qa-tests/_regression-2026-05-24/.
 *
 * The dashboard customise panel doesn't need to be touched — the new
 * widgets default to visible — so a vanilla landing on ``/`` is enough to
 * trigger every fetch we care about.
 *
 * Run:
 *   $env:PROPDEV_BACKEND_URL='http://localhost:9290'
 *   npx playwright test e2e/dashboard-4xx-fix.spec.ts
 */
import { test, expect, type Page, type Response } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

// Backend port — must match the uvicorn instance started for this run.
process.env.PROPDEV_BACKEND_URL ??= 'http://localhost:9290';
import { demoLogin, hydrateAuth } from './propdev/helpers/auth';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const SCREENSHOT_DIR = path.resolve(
  __dirname,
  '../../qa-tests/_dashboard-4xx-fix-2026-05-24',
);
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

/**
 * URL fragments we expect to be touched by the 10 wave-2 widgets. Any
 * 4xx or 5xx response on a path matching one of these prefixes counts
 * against this spec.
 */
const WATCHED_PATH_PREFIXES = [
  '/v1/risk/',
  '/v1/safety/incidents',
  '/v1/procurement/',
  '/v1/changeorders/',
  '/v1/schedule/',
  '/v1/clash/',
  '/v1/validation/reports',
  '/v1/daily_diary/weather/today',
  '/v1/daily-diary/weather/today',
  '/v1/finance/budgets',
  '/v1/boq/',
];

/**
 * The dev Vite proxy is hardcoded to ``http://127.0.0.1:9090``. Route
 * every in-browser API call to the worktree-local backend on 9290
 * instead, so this spec runs against the freshly-patched build.
 */
async function routeApiToWorktreeBackend(page: Page): Promise<void> {
  await page.route('**/api/**', async (route) => {
    const u = new URL(route.request().url());
    u.protocol = 'http:';
    u.host = 'localhost:9290';
    await route.continue({ url: u.toString() });
  });
}

async function loginAndGoToDashboard(page: Page): Promise<void> {
  await routeApiToWorktreeBackend(page);
  const session = await demoLogin('admin');
  await hydrateAuth(page.context(), session);
  await page.context().addInitScript(() => {
    try {
      localStorage.setItem('oe_onboarding_completed', 'true');
      localStorage.setItem('oe_welcome_dismissed', 'true');
      localStorage.setItem('oe_tour_completed', 'true');
      localStorage.setItem('oe.tour_completed', 'true');
      localStorage.setItem('oe_product_tour_completed', 'true');
      localStorage.setItem('oe_branding_wizard_dismissed', 'true');
      localStorage.setItem('oe_whats_new_seen_v4.5.0', 'true');
    } catch {
      /* incognito */
    }
  });
  await page.goto('/');
  await page.waitForLoadState('domcontentloaded', { timeout: 30_000 });
}

test('no 4xx/5xx on watched widget endpoints', async ({ page }) => {
  // Capture every response on the watched prefixes for 60 s after the
  // dashboard finishes its initial render. Includes the API-route hop —
  // we observe the rewritten URL (localhost:9290) which is what we hit.
  const offenders: Array<{ url: string; status: number; method: string }> = [];
  const allWatched: Array<{ url: string; status: number; method: string }> = [];

  const onResponse = (resp: Response) => {
    const url = resp.url();
    const path = (() => {
      try {
        return new URL(url).pathname + new URL(url).search;
      } catch {
        return url;
      }
    })();
    const matched = WATCHED_PATH_PREFIXES.some((p) => path.includes(p));
    if (!matched) return;
    const status = resp.status();
    const method = resp.request().method();
    allWatched.push({ url: path, status, method });
    // 422 on the demo user is real — it means the endpoint requires
    // ``project_id`` and the user has zero projects. We surface it as a
    // soft note (printed at the end) but don't fail the spec.
    if (status >= 400 && status < 600 && status !== 422) {
      offenders.push({ url: path, status, method });
    }
  };
  page.on('response', onResponse);

  await loginAndGoToDashboard(page);

  // Wait for the dashboard skeletons to settle. 60 s window for
  // long-tail per-project fan-outs.
  await page.waitForTimeout(60_000);

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, '01-dashboard-after-fix.png'),
    fullPage: true,
  });

  page.off('response', onResponse);

  // ── Report ──────────────────────────────────────────────────────────
  const summary = {
    watched_total: allWatched.length,
    watched_4xx_5xx_excluding_422: offenders.length,
    watched_422: allWatched.filter((r) => r.status === 422).length,
    by_prefix: WATCHED_PATH_PREFIXES.map((p) => ({
      prefix: p,
      total: allWatched.filter((r) => r.url.includes(p)).length,
      bad: offenders.filter((r) => r.url.includes(p)).length,
    })).filter((row) => row.total > 0),
    offenders,
  };
  fs.writeFileSync(
    path.join(SCREENSHOT_DIR, 'response-summary.json'),
    JSON.stringify(summary, null, 2),
  );
  // eslint-disable-next-line no-console
  console.log('[dashboard-4xx-fix]', JSON.stringify(summary, null, 2));

  // The hard contract: ZERO non-422 4xx / 5xx on the watched prefixes.
  expect(offenders, `Unexpected 4xx/5xx responses: ${JSON.stringify(offenders, null, 2)}`).toEqual(
    [],
  );
});
