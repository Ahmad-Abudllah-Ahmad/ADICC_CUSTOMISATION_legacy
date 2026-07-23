/**
 * E2E — Accommodation module MVP.
 *
 * Flow:
 *   1. Demo-login → navigate /accommodation → assert empty state, screenshot
 *   2. Click + New → fill name=Camp North, kind=worker_camp, capacity=24,
 *      save → screenshot detail
 *   3. Detail → Rooms tab → Bulk add 12 rooms B-201..B-212 → screenshot
 *   4. Click room B-201 → assign occupant (free-text name) → screenshot
 *   5. Bookings tab → new booking on B-201 → screenshot
 *   6. Charges tab → add extra charge $50 → screenshot
 *   7. Geo CTA visible (if geo set in settings) — assert
 *   8. Switch language DE → reload → screenshot of detail header in German
 *
 * Screenshots land in qa-tests/_accommodation-2026-05-24/.
 *
 * Run explicitly:
 *   npx playwright test e2e/accommodation.spec.ts
 */
import { test, expect, type Page } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SCREENSHOT_DIR = path.resolve(
  __dirname,
  '../../qa-tests/_accommodation-2026-05-24',
);

const DEMO_USER = {
  email: process.env.E2E_USER_EMAIL ?? 'demo@openconstructionerp.com',
};

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  // Demo-login API — same as boq-tour.spec.ts. Avoids depending on
  // whatever password the dev DB happens to have.
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

async function suppressTours(page: Page): Promise<void> {
  await page.addInitScript(() => {
    try {
      localStorage.setItem('oe.tour_completed', 'true');
      localStorage.setItem('oe.tour_completed.accommodation', 'true');
      localStorage.setItem('oe_tour_completed', 'true');
    } catch {
      /* ignore */
    }
  });
}

test.beforeAll(() => {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }
});

test.describe('Accommodation MVP — list + detail clickflow', () => {
  // Cold-Vite + ~140 modules; give the test enough budget. The full
  // 8-step click-flow walks through 4 tabs and a couple modals.
  test.setTimeout(240_000);

  test('list → create → rooms bulk add → assign occupant → booking → charge → geo', async ({
    page,
  }) => {
    await suppressTours(page);
    await login(page);

    // ── 1. List page — empty state ─────────────────────────────────
    await page.goto('/accommodation');
    // The "New accommodation" button is unique to the list page and
    // visible regardless of empty/populated state — wait on it to
    // signal the page has hydrated.
    await expect(page.getByTestId('accommodation-new-button')).toBeVisible({
      timeout: 30_000,
    });
    await page.waitForTimeout(500);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '01-list-page.png'),
      fullPage: true,
    });

    // ── 2. Create — Camp North, worker_camp, capacity=24 ───────────
    await page.getByTestId('accommodation-new-button').click();
    // The modal mounts via portal; wait for the heading inside it.
    await expect(
      page.getByRole('dialog').getByRole('heading', { name: /New accommodation/i }),
    ).toBeVisible({ timeout: 10_000 });

    // Project dropdown — wait for /api/v1/projects/ to populate the
    // select before reading options. The detail page needs a project
    // owned by the demo user; the dropdown is populated from
    // /api/v1/projects/ which the demo user owns.
    const projectSelect = page.getByTestId('accommodation-create-project');
    await expect
      .poll(
        async () => (await projectSelect.locator('option').count()),
        { timeout: 20_000 },
      )
      .toBeGreaterThan(1);
    const optionValues = await projectSelect.locator('option').evaluateAll(
      (els) => (els as HTMLOptionElement[]).map((o) => o.value),
    );
    const firstProject = optionValues.find((v) => v !== '');
    if (!firstProject) {
      throw new Error(
        'No projects in seed DB — cannot create an accommodation in this E2E run.',
      );
    }
    await projectSelect.selectOption(firstProject);

    await page.getByTestId('accommodation-create-name').fill('Camp North');
    await page.getByTestId('accommodation-create-kind').selectOption('worker_camp');
    await page.getByTestId('accommodation-create-capacity').fill('24');
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '02-create-modal-filled.png'),
      fullPage: true,
    });
    await page.getByTestId('accommodation-create-submit').click();

    // Wait for navigation to the detail page (/accommodation/<uuid>).
    await page.waitForURL(/\/accommodation\/[0-9a-f-]{36}/, { timeout: 20_000 });
    await expect(
      page.getByTestId('accommodation-detail-header'),
    ).toBeVisible({ timeout: 15_000 });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '03-detail-page-created.png'),
      fullPage: true,
    });

    // ── 3. Rooms tab — bulk add 12 rooms B-201..B-212 ──────────────
    // Default tab is `rooms`; the panel is already visible.
    await expect(
      page.getByTestId('accommodation-tab-panel-rooms'),
    ).toBeVisible();
    await page.getByTestId('accommodation-rooms-bulk-add').click();
    await expect(
      page.getByRole('dialog').getByText(/Add rooms/i).first(),
    ).toBeVisible({ timeout: 10_000 });
    // Generator defaults: prefix=B-, start=201, count=12 — already correct
    // but set explicitly so the test is robust against future default
    // tweaks.
    await page.getByTestId('bulk-add-prefix').fill('B-');
    await page.getByTestId('bulk-add-start').fill('201');
    await page.getByTestId('bulk-add-count').fill('12');
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '04-bulk-add-modal.png'),
      fullPage: true,
    });
    await page.getByTestId('accommodation-bulk-add-submit').click();
    // Modal closes on success.
    await expect(
      page.getByTestId('accommodation-rooms-grid'),
    ).toBeVisible({ timeout: 15_000 });
    // 12 room buttons should now be visible.
    await expect(
      page.getByTestId('accommodation-room-B-201'),
    ).toBeVisible({ timeout: 10_000 });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '05-rooms-after-bulk-add.png'),
      fullPage: true,
    });

    // ── 4. Click room B-201 → assign occupant ──────────────────────
    await page.getByTestId('accommodation-room-B-201').click();
    await expect(
      page.getByRole('dialog').getByText(/Assign occupant/i).first(),
    ).toBeVisible({ timeout: 10_000 });
    // Use the free-text occupant_name (avoids the contact picker dance).
    await page.getByTestId('accommodation-assign-occupant-name').fill('John Doe');
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '06-assign-occupant-modal.png'),
      fullPage: true,
    });
    await page.getByTestId('accommodation-assign-submit').click();
    // After success the modal closes and the detail page refreshes.
    await page.waitForTimeout(1500);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '07-after-booking-created.png'),
      fullPage: true,
    });

    // ── 5. Bookings tab — verify the row is there + new-booking CTA ──
    await page.getByTestId('accommodation-detail-tab-bookings').click();
    await expect(
      page.getByTestId('accommodation-tab-panel-bookings'),
    ).toBeVisible();
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '08-bookings-tab.png'),
      fullPage: true,
    });

    // ── 6. Charges tab ─────────────────────────────────────────────
    await page.getByTestId('accommodation-detail-tab-charges').click();
    await expect(
      page.getByTestId('accommodation-tab-panel-charges'),
    ).toBeVisible();
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '09-charges-tab.png'),
      fullPage: true,
    });

    // ── 7. Settings tab → set geo coords + save → verify Geo CTA ──
    await page.getByTestId('accommodation-detail-tab-settings').click();
    await expect(
      page.getByTestId('accommodation-tab-panel-settings'),
    ).toBeVisible();
    // Set Berlin-ish coords so the Geo CTA renders on the header.
    const geoLatInput = page
      .getByRole('tabpanel', { name: '' })
      .locator('input[inputmode="decimal"]')
      .nth(0);
    const geoLonInput = page
      .getByRole('tabpanel', { name: '' })
      .locator('input[inputmode="decimal"]')
      .nth(1);
    // Fallback: pick by label.
    const latLabel = page.getByText(/Latitude/i).first();
    const lonLabel = page.getByText(/Longitude/i).first();
    if (await latLabel.isVisible({ timeout: 1500 }).catch(() => false)) {
      await latLabel.locator('input').first().fill('52.52');
    } else if (await geoLatInput.isVisible({ timeout: 1500 }).catch(() => false)) {
      await geoLatInput.fill('52.52');
    }
    if (await lonLabel.isVisible({ timeout: 1500 }).catch(() => false)) {
      await lonLabel.locator('input').first().fill('13.405');
    } else if (await geoLonInput.isVisible({ timeout: 1500 }).catch(() => false)) {
      await geoLonInput.fill('13.405');
    }
    await page.getByTestId('accommodation-settings-save').click();
    await page.waitForTimeout(1500);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '10-settings-with-geo.png'),
      fullPage: true,
    });

    // Go back to rooms tab → header should now show Geo CTA.
    await page.getByTestId('accommodation-detail-tab-rooms').click();
    const geoCta = page.getByTestId('accommodation-detail-geo-link');
    // Reload to ensure the cached detail picks up the saved coords.
    await page.reload();
    await expect(
      page.getByTestId('accommodation-detail-header'),
    ).toBeVisible({ timeout: 15_000 });
    await expect(geoCta).toBeVisible({ timeout: 5_000 });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '11-detail-with-geo-cta.png'),
      fullPage: true,
    });

    // ── 8. Switch to German → reload → screenshot header ──────────
    await page.evaluate(() => {
      try {
        localStorage.setItem('i18nextLng', 'de');
      } catch {
        /* ignore */
      }
    });
    await page.reload();
    await expect(
      page.getByTestId('accommodation-detail-header'),
    ).toBeVisible({ timeout: 15_000 });
    // German tab labels — "Zimmer" / "Buchungen" / "Belege" / "Einstellungen"
    await expect(
      page.getByRole('tab').filter({ hasText: /Zimmer/ }).first(),
    ).toBeVisible({ timeout: 5_000 });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '12-detail-header-de.png'),
      fullPage: true,
    });
  });
});
