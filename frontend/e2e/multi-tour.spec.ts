/**
 * E2E — Multi-module Tour smoke test.
 *
 * For each of the 5 per-module tours added on top of the BOQ reference:
 *
 *   - bim          → /bim
 *   - geo          → /geo
 *   - propdev      → /property-dev
 *   - accommodation→ /accommodation (list) → first card detail page
 *   - dashboard    → / (dashboard)
 *
 * Flow per tour:
 *   1. Demo-login.
 *   2. Navigate to the module page.
 *   3. Click the per-module Tour button (`module-help-button-<tourId>`).
 *   4. Screenshot step 1.
 *   5. Walk through every step via the Next button.
 *   6. Finish — assert localStorage `oe.tour_completed.<tourId>` === 'true'.
 *
 * Plus: switch the UI to German for ONE of the 5 tours (BIM — most
 * user-visible 3D surface) → screenshot to prove German rendering.
 *
 * Screenshots land in qa-tests/_multi-tour-2026-05-24/<tourId>/.
 *
 * Run explicitly:
 *   npx playwright test e2e/multi-tour.spec.ts
 */
import { test, expect, type Page } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SCREENSHOT_ROOT = path.resolve(
  __dirname,
  '../../qa-tests/_multi-tour-2026-05-24',
);

const DEMO_USER = {
  email: process.env.E2E_USER_EMAIL ?? 'demo@openconstructionerp.com',
};

// ── Helpers ──────────────────────────────────────────────────────────────

async function login(page: Page): Promise<void> {
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

/**
 * Suppress the auto-launching global tour AND the per-module tour we're
 * about to launch — we want a *clean* slate so clicking the per-module
 * Tour button is what surfaces the tour, not a stale auto-launch.
 */
async function suppressTours(page: Page, tourId: string): Promise<void> {
  await page.addInitScript((id) => {
    try {
      localStorage.setItem('oe.tour_completed', 'true');
      localStorage.setItem(`oe.tour_completed.${id}`, 'false');
      localStorage.setItem('oe_tour_completed', 'true');
    } catch {
      /* ignore */
    }
  }, tourId);
}

/**
 * Set the UI language by stamping i18next's localStorage key + reloading.
 * Same mechanism the in-app language picker uses.
 */
async function setLocale(page: Page, lang: string): Promise<void> {
  await page.addInitScript((l) => {
    try {
      localStorage.setItem('i18nextLng', l);
      localStorage.setItem('oe_lang', l);
    } catch {
      /* ignore */
    }
  }, lang);
}

/**
 * Walk a tour to completion via Next clicks; screenshot every step into
 * `outDir`. Returns the total step count actually walked.
 */
async function walkTour(page: Page, outDir: string): Promise<number> {
  const tooltip = page.getByTestId('product-tour-tooltip');
  await expect(tooltip).toBeVisible({ timeout: 10_000 });

  // Take screenshot of step 1 first.
  await page.waitForTimeout(400); // let spotlight settle
  await page.screenshot({
    path: path.join(outDir, 'step-01.png'),
    fullPage: true,
  });

  let step = 1;
  const MAX_STEPS = 12;
  while (step < MAX_STEPS) {
    const next = page.getByTestId('product-tour-next');
    if (!(await next.isVisible().catch(() => false))) break;
    const label = (await next.getAttribute('aria-label')) ?? '';
    await next.click();
    step += 1;
    // The Finish button click closes the tour entirely.
    if (/finish/i.test(label)) {
      // Wait for tooltip to disappear.
      await expect(tooltip).toBeHidden({ timeout: 5_000 });
      break;
    }
    await page.waitForTimeout(350);
    await page.screenshot({
      path: path.join(outDir, `step-${String(step).padStart(2, '0')}.png`),
      fullPage: true,
    });
  }
  return step;
}

async function ensureDir(dir: string): Promise<void> {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

test.beforeAll(() => {
  ensureDir(SCREENSHOT_ROOT);
});

// ── Per-tour navigators ──────────────────────────────────────────────────

interface TourDescriptor {
  id: string;
  /** Navigate the page so the Tour button mounts. Return when ready. */
  goto: (page: Page) => Promise<void>;
}

const TOURS: TourDescriptor[] = [
  {
    id: 'dashboard',
    goto: async (page) => {
      await page.goto('/');
      await expect(
        page.getByTestId('module-help-button-dashboard'),
      ).toBeVisible({ timeout: 20_000 });
    },
  },
  {
    id: 'bim',
    goto: async (page) => {
      await page.goto('/bim');
      await expect(
        page.getByTestId('module-help-button-bim'),
      ).toBeVisible({ timeout: 25_000 });
    },
  },
  {
    id: 'geo',
    goto: async (page) => {
      await page.goto('/geo');
      await expect(
        page.getByTestId('module-help-button-geo'),
      ).toBeVisible({ timeout: 25_000 });
    },
  },
  {
    id: 'propdev',
    goto: async (page) => {
      await page.goto('/property-dev');
      await expect(
        page.getByTestId('module-help-button-propdev'),
      ).toBeVisible({ timeout: 25_000 });
    },
  },
  {
    id: 'accommodation',
    goto: async (page) => {
      await page.goto('/accommodation');
      // Detail page is where the Tour button mounts; pick the first
      // card if any exists, else stay on list (button mounts there too).
      await page.waitForTimeout(800);
      const card = page.locator('[data-testid^="accommodation-card-"]').first();
      if (await card.isVisible().catch(() => false)) {
        await card.click();
      }
      await expect(
        page.getByTestId('module-help-button-accommodation'),
      ).toBeVisible({ timeout: 25_000 });
    },
  },
];

// ── Per-tour test cases ──────────────────────────────────────────────────

for (const tour of TOURS) {
  test.describe(`Tour: ${tour.id}`, () => {
    test.setTimeout(180_000);

    test(`launches via ModuleHelpButton and walks to completion (${tour.id})`, async ({
      page,
    }) => {
      const outDir = path.join(SCREENSHOT_ROOT, tour.id);
      ensureDir(outDir);

      await suppressTours(page, tour.id);
      await login(page);

      await tour.goto(page);

      // Click the per-module Tour CTA.
      await page.getByTestId(`module-help-button-${tour.id}`).click();

      // Walk every step.
      const stepsWalked = await walkTour(page, outDir);
      expect(stepsWalked).toBeGreaterThanOrEqual(2);

      // The Finish click should have written the completion flag.
      const completed = await page.evaluate(
        (id) => localStorage.getItem(`oe.tour_completed.${id}`),
        tour.id,
      );
      expect(completed).toBe('true');
    });
  });
}

// ── DE locale sanity-check — BIM tour ────────────────────────────────────

test.describe('Tour DE: bim (German rendering)', () => {
  test.setTimeout(180_000);

  test('renders bim tour step 1 in German', async ({ page }) => {
    const outDir = path.join(SCREENSHOT_ROOT, 'bim-de');
    ensureDir(outDir);

    await setLocale(page, 'de');
    await suppressTours(page, 'bim');
    await login(page);

    await page.goto('/bim');
    await expect(
      page.getByTestId('module-help-button-bim'),
    ).toBeVisible({ timeout: 25_000 });

    await page.getByTestId('module-help-button-bim').click();
    const tooltip = page.getByTestId('product-tour-tooltip');
    await expect(tooltip).toBeVisible({ timeout: 10_000 });
    await page.waitForTimeout(500);

    // Sanity: the German title for step 1 is "Modell-Filmstreifen".
    await expect(tooltip).toContainText(/Modell-Filmstreifen/i, {
      timeout: 5_000,
    });
    await page.screenshot({
      path: path.join(outDir, 'step-01-de.png'),
      fullPage: true,
    });
  });
});
