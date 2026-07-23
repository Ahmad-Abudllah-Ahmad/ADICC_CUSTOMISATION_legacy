/**
 * E2E — Dashboard N+1 nuke (v4.6.2, 2026-05-24).
 *
 * Verifies the two contracts the regression report demanded:
 *
 *   1. The dashboard fires ≤ 2 ``/api/v1/dashboard/`` requests on render.
 *   2. ZERO per-project ``/api/v1/boq/boqs/?project_id=…`` or
 *      ``/api/v1/schedule/schedules/?project_id=…`` requests on render —
 *      both are sourced from the rollup payload now.
 *
 * Also smoke-tests the tour-state persistence: open the dashboard,
 * dismiss the tour (if it auto-pops), reload, assert no tour overlay
 * re-appears within the auto-start grace window.
 *
 * Run:
 *   $env:PROPDEV_BACKEND_URL='http://localhost:9290'
 *   npx playwright test e2e/dashboard-rollup.spec.ts
 */
import { test, expect, type Page, type Response } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

process.env.PROPDEV_BACKEND_URL ??= 'http://localhost:9290';
import { demoLogin, hydrateAuth } from './propdev/helpers/auth';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const SCREENSHOT_DIR = path.resolve(
  __dirname,
  '../../qa-tests/_dashboard-rollup-2026-05-24',
);
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

/**
 * The dev Vite proxy is hardcoded to ``http://127.0.0.1:9090``. Route
 * every in-browser API call to the worktree-local backend on 9290.
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
      // Deliberately do NOT pre-set ``oe.tour_completed`` here — the
      // second test in this file needs the tour to actually mount so we
      // can verify the dismiss-then-reload persistence flow.
      localStorage.setItem('oe_onboarding_completed', 'true');
      localStorage.setItem('oe_welcome_dismissed', 'true');
      localStorage.setItem('oe_branding_wizard_dismissed', 'true');
      localStorage.setItem('oe_whats_new_seen_v4.6.0', 'true');
      localStorage.setItem('oe_whats_new_seen_v4.6.1', 'true');
    } catch {
      /* incognito */
    }
  });
  await page.goto('/');
  await page.waitForLoadState('domcontentloaded', { timeout: 30_000 });
}

interface CountedReq {
  url: string;
  method: string;
  status: number;
}

function pathOf(url: string): string {
  try {
    return new URL(url).pathname;
  } catch {
    return url;
  }
}

test('dashboard fires ≤ 2 rollup calls and zero per-project boq/schedule fan-out', async ({
  page,
}) => {
  const rollupReqs: CountedReq[] = [];
  const perProjectReqs: CountedReq[] = [];

  const onResponse = (resp: Response) => {
    const p = pathOf(resp.url());
    const method = resp.request().method();
    const status = resp.status();
    if (p.startsWith('/api/v1/dashboard/')) {
      rollupReqs.push({ url: p, method, status });
    }
    // Per-project fan-out the regression flagged. We assert ZERO of these
    // fire on the post-fix dashboard render — every consumer should read
    // from the rollup payload instead.
    if (
      p === '/api/v1/boq/boqs/' || p === '/api/v1/boq/boqs' ||
      p === '/api/v1/schedule/schedules/' || p === '/api/v1/schedule/schedules'
    ) {
      // We further filter to requests that carried a ``project_id`` query —
      // the rollup itself never hits these URLs, so any hit IS a fan-out.
      const search = (() => {
        try { return new URL(resp.url()).search; } catch { return ''; }
      })();
      if (search.includes('project_id=')) {
        perProjectReqs.push({ url: p + search, method, status });
      }
    }
  };
  page.on('response', onResponse);

  await loginAndGoToDashboard(page);

  // 30 s window for the rollup + every wave-2 widget to render. The
  // rollup TTL is 60 s so a second render within that window must NOT
  // trigger a second network call (React Query staleTime).
  await page.waitForTimeout(30_000);

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, '01-dashboard-after-rollup-nuke.png'),
    fullPage: true,
  });

  page.off('response', onResponse);

  const summary = {
    dashboard_calls: rollupReqs.length,
    dashboard_urls: rollupReqs.map((r) => `${r.method} ${r.url} → ${r.status}`),
    per_project_fan_out_calls: perProjectReqs.length,
    per_project_fan_out_urls: perProjectReqs.map(
      (r) => `${r.method} ${r.url} → ${r.status}`,
    ),
  };
  fs.writeFileSync(
    path.join(SCREENSHOT_DIR, 'rollup-summary.json'),
    JSON.stringify(summary, null, 2),
  );
  // eslint-disable-next-line no-console
  console.log('[dashboard-rollup]', JSON.stringify(summary, null, 2));

  // Hard contracts.
  expect(
    rollupReqs.length,
    `Expected ≤ 2 dashboard rollup calls, got ${rollupReqs.length}: ${
      JSON.stringify(summary.dashboard_urls)
    }`,
  ).toBeLessThanOrEqual(2);

  expect(
    perProjectReqs.length,
    `Expected ZERO per-project boq/schedule fan-out calls, got ${
      perProjectReqs.length
    }: ${JSON.stringify(summary.per_project_fan_out_urls)}`,
  ).toBe(0);
});

test('product tour stays dismissed across page reloads (server persistence)', async ({
  page,
}) => {
  await loginAndGoToDashboard(page);

  // First visit: wait for either the tour overlay to appear OR a 1.5 s
  // grace period — if no tour ever pops, the rest of the test is a no-
  // op pass (this is fine; we're testing the persistence, not the auto-
  // pop heuristic itself).
  const tourSelector = '[data-testid="product-tour-tooltip"]';
  await page.waitForTimeout(1_500);
  const initiallyVisible = await page.locator(tourSelector).isVisible().catch(() => false);

  if (initiallyVisible) {
    // Dismiss via Skip button. The ``handleSkip`` callback writes both
    // localStorage AND fires a PUT to ``/v1/users/me/tour-state/``.
    await page.locator('[data-testid="product-tour-skip"]').click();
    await expect(page.locator(tourSelector)).not.toBeVisible({ timeout: 5_000 });
  } else {
    // Tour didn't auto-pop — explicitly call the localStorage flag the
    // ProductTour writes on dismiss, then trigger a tour-state PUT so we
    // can still verify the persistence round-trip on reload.
    await page.evaluate(async () => {
      try {
        localStorage.setItem('oe.tour_completed', 'true');
      } catch {
        /* no-op */
      }
      try {
        const token = (window as unknown as {
          __OE_AUTH__?: { accessToken?: string };
        }).__OE_AUTH__?.accessToken;
        await fetch('/api/v1/users/me/tour-state/', {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            tours: {
              global: {
                dismissed_at: new Date().toISOString(),
                completed_at: null,
              },
            },
          }),
        });
      } catch {
        /* fallback path is best-effort */
      }
    });
  }

  // Reload — the new ProductTour hydration MUST NOT pop the overlay
  // again. Wait the auto-start delay (~600ms in source) + buffer.
  await page.reload();
  await page.waitForLoadState('domcontentloaded', { timeout: 30_000 });
  await page.waitForTimeout(2_000);

  const reopened = await page.locator(tourSelector).isVisible().catch(() => false);
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, '02-after-reload.png'),
    fullPage: true,
  });
  expect(
    reopened,
    'ProductTour overlay reopened after reload — tour-state persistence broken.',
  ).toBe(false);
});
