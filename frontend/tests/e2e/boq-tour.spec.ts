/**
 * E2E — Per-module guided tour for the BOQ Editor.
 *
 * Flow:
 *   1. Demo-login → pick first project that has at least one BOQ → open it.
 *   2. Assert the new "Tour" ModuleHelpButton is visible in the page header.
 *   3. Click Tour → assert the ProductTour overlay + tooltip render.
 *   4. Screenshot every step in English (8 steps).
 *   5. Click Finish → assert overlay disappears and localStorage flag is set.
 *   6. Reload → assert tour does NOT auto-launch, but the Tour button can
 *      relaunch it (idempotency check).
 *   7. Switch UI language to German → relaunch tour → screenshot step 1.
 *
 * Screenshots land in qa-tests/_boq-tour-2026-05-24/.
 *
 * Run explicitly:
 *   npx playwright test tests/e2e/boq-tour.spec.ts
 */
import { test, expect, type Page } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SCREENSHOT_DIR = path.resolve(
  __dirname,
  '../../../qa-tests/_boq-tour-2026-05-24',
);

const DEMO_USER = {
  email: process.env.E2E_USER_EMAIL ?? 'demo@openconstructionerp.com',
  password: process.env.E2E_USER_PASSWORD ?? 'DemoPass1234!',
};

async function login(page: Page): Promise<void> {
  // Use the demo-login API directly — avoids depending on whatever
  // password the dev DB happens to have for the demo user. This mirrors
  // the production "Demo login" button flow.
  await page.goto('/login');
  const res = await page.request.post('/api/v1/users/auth/demo-login/', {
    headers: { 'Content-Type': 'application/json' },
    data: { email: DEMO_USER.email },
  });
  if (!res.ok()) {
    throw new Error(`demo-login returned ${res.status()}`);
  }
  const body = await res.json();
  if (!body.access_token) {
    throw new Error('demo-login response missing access_token');
  }
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
    { tok: body.access_token, refresh: body.refresh_token, email: DEMO_USER.email },
  );
  await page.goto('/');
  await expect(page).not.toHaveURL(/\/login/, { timeout: 20_000 });
}

async function openAnyBOQ(page: Page): Promise<void> {
  // Pull the token the app stored so we can hit /api/v1 directly to find
  // a BOQ to open without scraping the UI list page.
  const token = await page.evaluate(
    () =>
      sessionStorage.getItem('oe_access_token') ??
      localStorage.getItem('oe_access_token'),
  );
  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  const projRes = await page.request.get('/api/v1/projects/?limit=20', {
    headers,
  });
  if (!projRes.ok()) {
    throw new Error(`GET /projects/ returned ${projRes.status()}`);
  }
  const projBody = await projRes.json();
  const projects: { id: string }[] = Array.isArray(projBody)
    ? projBody
    : projBody.items ?? [];
  if (projects.length === 0) throw new Error('No projects in seed DB.');

  // Find a project that has at least one BOQ.
  let boqId: string | null = null;
  for (const p of projects) {
    const r = await page.request.get(
      `/api/v1/boq/boqs/?project_id=${p.id}&limit=1`,
      { headers },
    );
    if (!r.ok()) continue;
    const body = await r.json();
    const items: { id: string }[] = Array.isArray(body)
      ? body
      : body.items ?? [];
    if (items.length > 0) {
      boqId = items[0].id;
      break;
    }
  }
  if (!boqId) {
    throw new Error('No BOQs found across the first 20 seed projects.');
  }

  await page.goto(`/boq/${boqId}`);
  // Wait for either the toolbar (always present) or the empty-BOQ state.
  await page.waitForSelector('[data-testid="boq-toolbar"]', {
    timeout: 25_000,
  });
}

/** Suppress the auto-start of the global tour so it doesn't race the BOQ
 *  tour during this spec. */
async function suppressGlobalTour(page: Page): Promise<void> {
  await page.addInitScript(() => {
    try {
      localStorage.setItem('oe.tour_completed', 'true');
    } catch {
      /* ignore */
    }
  });
}

async function clearBoqTourCompletion(page: Page): Promise<void> {
  await page.evaluate(() => {
    try {
      localStorage.removeItem('oe.tour_completed.boq');
    } catch {
      /* ignore */
    }
  });
}

async function setLanguage(page: Page, lang: string): Promise<void> {
  // Persist to the i18next localStorage key (the language detector reads
  // this on bootstrap) and reload — i18next isn't exposed on `window` in
  // production builds so a runtime changeLanguage isn't reliable.
  await page.evaluate((code) => {
    try {
      localStorage.setItem('i18nextLng', code);
    } catch {
      /* ignore */
    }
  }, lang);
  await page.reload();
  await page.waitForSelector('[data-testid="boq-toolbar"]', {
    timeout: 25_000,
  });
}

test.beforeAll(() => {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }
});

test.describe('BOQ Editor — per-module guided tour', () => {
  // Heavy spec — 8 spotlight steps × screenshot + reload + relaunch +
  // confirm dance. Default 30 s is too tight on a cold Vite that's
  // serving ~140 modules.
  test.setTimeout(180_000);

  test('Tour button launches the 8-step BOQ tour + persists completion', async ({
    page,
  }) => {
    await suppressGlobalTour(page);
    await login(page);
    await openAnyBOQ(page);
    await clearBoqTourCompletion(page);

    // 1. The new Tour button is visible in the page header.
    const tourBtn = page.getByTestId('module-help-button-boq');
    await expect(tourBtn).toBeVisible({ timeout: 10_000 });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'tour-button-visible.png'),
      fullPage: false,
    });

    // 2. Click Tour → overlay + first-step tooltip.
    await tourBtn.click();
    const tooltip = page.getByTestId('product-tour-tooltip');
    await expect(tooltip).toBeVisible({ timeout: 5_000 });
    await expect(page.getByTestId('product-tour-step-counter')).toContainText(
      /1\s*\/?\s*of?\s*8|Step\s*1/i,
    );
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'step-1-en.png'),
      fullPage: true,
    });

    // 3. Walk through steps 2-8, screenshotting each.
    for (let step = 2; step <= 8; step++) {
      await page.getByTestId('product-tour-next').click();
      await expect(tooltip).toBeVisible({ timeout: 5_000 });
      // Let the spotlight settle (positionForStep has a 180ms delay).
      await page.waitForTimeout(300);
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, `step-${step}-en.png`),
        fullPage: true,
      });
    }

    // 4. Finish — last click closes the overlay and writes the flag.
    await page.getByTestId('product-tour-next').click();
    await expect(tooltip).toBeHidden({ timeout: 5_000 });

    const completed = await page.evaluate(() =>
      localStorage.getItem('oe.tour_completed.boq'),
    );
    expect(completed).toBe('true');

    // 5. Reload — the tour does not auto-launch on a module page, and the
    //    Tour button is still ready to relaunch it.
    await page.reload();
    await page.waitForSelector('[data-testid="boq-toolbar"]', {
      timeout: 25_000,
    });
    await expect(page.getByTestId('product-tour-tooltip')).toBeHidden();
    await expect(page.getByTestId('module-help-button-boq')).toBeVisible();
    await page.getByTestId('module-help-button-boq').click();
    await expect(page.getByTestId('product-tour-tooltip')).toBeVisible({
      timeout: 5_000,
    });
    // Close it so the next German test starts clean.
    await page.getByTestId('product-tour-skip').click();
    // The Esc-style skip pops a confirm — accept it.
    const confirmBtn = page
      .getByRole('button', { name: /exit tour|tour beenden|Выйти|выход/i })
      .first();
    if (await confirmBtn.isVisible({ timeout: 1_500 }).catch(() => false)) {
      await confirmBtn.click();
    }
    await expect(page.getByTestId('product-tour-tooltip')).toBeHidden({
      timeout: 5_000,
    });
  });

  test('German locale — first step renders translated copy', async ({
    page,
  }) => {
    await suppressGlobalTour(page);
    await login(page);
    await openAnyBOQ(page);
    await clearBoqTourCompletion(page);
    await setLanguage(page, 'de');

    // Re-fetch the button after language switch (component re-rendered).
    const tourBtn = page.getByTestId('module-help-button-boq');
    await expect(tourBtn).toBeVisible({ timeout: 10_000 });
    await tourBtn.click();

    const tooltip = page.getByTestId('product-tour-tooltip');
    await expect(tooltip).toBeVisible({ timeout: 5_000 });
    // The German title is "LV-Werkzeugleiste" — assert it lands.
    await expect(tooltip).toContainText(/LV-Werkzeugleiste/);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'step-1-de.png'),
      fullPage: true,
    });
  });
});
