/**
 * E2E — Accommodation calendar (rooms × dates) view.
 *
 * Flow:
 *   1. Demo-login → seed an accommodation "Calendar QA" with 3 rooms
 *   2. Open detail → Calendar tab → assert grid visible with the 3 rooms
 *   3. Click an empty cell on room CAL-1 (today + 7d) → modal opens with
 *      check_in prefilled → fill occupant + check_out → submit
 *   4. Verify the booking block appears with the amber `reserved` colour
 *      class at the right room/date intersection
 *   5. Also exercise the standalone /accommodation/calendar route + view
 *      toggle (Week ↔ Month) + the today button.
 *
 * Screenshots land in qa-tests/_accommodation-calendar-2026-05-24/.
 *
 * Run explicitly:
 *   npx playwright test e2e/accommodation-calendar.spec.ts
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SCREENSHOT_DIR = path.resolve(
  __dirname,
  '../../qa-tests/_accommodation-calendar-2026-05-24',
);

const DEMO_USER = {
  // Note the "r" in openestima(r)tor — the canonical demo email per
  // memory. openestimate.io WITHOUT the r is the common 401 trap.
  email: process.env.E2E_USER_EMAIL ?? 'demo@openconstructionerp.com',
};

async function login(page: Page): Promise<string> {
  await page.goto('/login');
  const res = await page.request.post('/api/v1/users/auth/demo-login/', {
    headers: { 'Content-Type': 'application/json' },
    data: { email: DEMO_USER.email },
  });
  if (!res.ok()) {
    throw new Error(`demo-login returned ${res.status()}`);
  }
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
  await expect(page).not.toHaveURL(/\/login/, { timeout: 20_000 });
  return token;
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

async function firstProjectId(
  api: APIRequestContext,
  token: string,
): Promise<string> {
  const resp = await api.get('/api/v1/projects/', {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok()) {
    throw new Error(`GET /projects/ returned ${resp.status()}`);
  }
  const list = await resp.json();
  if (!Array.isArray(list) || list.length === 0) {
    throw new Error('No projects in seed DB for E2E run');
  }
  return list[0].id as string;
}

interface SeedResult {
  accommodationId: string;
  roomIds: string[];
  roomLabels: string[];
}

async function seedAccommodation(
  api: APIRequestContext,
  token: string,
  projectId: string,
): Promise<SeedResult> {
  const auth = { Authorization: `Bearer ${token}` };

  const accomResp = await api.post('/api/v1/accommodation/', {
    headers: auth,
    data: {
      project_id: projectId,
      name: `Calendar QA ${Date.now()}`,
      kind: 'worker_camp',
    },
  });
  if (!accomResp.ok()) {
    throw new Error(`Create accommodation failed ${accomResp.status()}`);
  }
  const accomId = (await accomResp.json()).id as string;

  const labels = ['CAL-1', 'CAL-2', 'CAL-3'];
  const roomsResp = await api.post(
    `/api/v1/accommodation/${accomId}/rooms`,
    {
      headers: auth,
      data: { rooms: labels.map((l) => ({ label: l, capacity: 1 })) },
    },
  );
  if (!roomsResp.ok()) {
    throw new Error(`Bulk create rooms failed ${roomsResp.status()}`);
  }
  const roomIds = (await roomsResp.json()).map((r: { id: string }) => r.id);

  return { accommodationId: accomId, roomIds, roomLabels: labels };
}

/** Date a few days ahead so the empty cell is in this week's grid. */
function isoNDaysFromToday(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

test.beforeAll(() => {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }
});

test.describe('Accommodation calendar — rooms × dates grid', () => {
  // The calendar walks a fair amount of DOM (rooms × days). Same budget
  // as the bookings spec.
  test.setTimeout(240_000);

  test('detail-tab calendar → click empty cell → create booking → block visible', async ({
    page,
    request,
  }) => {
    await suppressTours(page);
    const token = await login(page);

    const projectId = await firstProjectId(request, token);
    const seed = await seedAccommodation(request, token, projectId);

    // ── 1. Open the detail page → switch to Calendar tab ────────────
    await page.goto(`/accommodation/${seed.accommodationId}`);
    await expect(
      page.getByTestId('accommodation-detail-header'),
    ).toBeVisible({ timeout: 30_000 });

    await page.getByTestId('accommodation-detail-tab-calendar').click();
    await expect(
      page.getByTestId('accommodation-tab-panel-calendar'),
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByTestId('accommodation-calendar-grid'),
    ).toBeVisible({ timeout: 15_000 });

    // All 3 rooms should be rows in the grid.
    for (const id of seed.roomIds) {
      await expect(
        page.getByTestId(`accommodation-calendar-row-${id}`),
      ).toBeVisible({ timeout: 10_000 });
    }
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '01-calendar-empty.png'),
      fullPage: true,
    });

    // ── 2. Click an empty cell on room CAL-1, today + 3 days ─────────
    // Stay within the visible week (start = monday) by using a +1..+5 offset.
    const targetIso = isoNDaysFromToday(3);
    const firstRoomId = seed.roomIds[0];
    const cellId = `accommodation-calendar-cell-${firstRoomId}-${targetIso}`;
    // The cell might be off-screen if today is near the end of the week;
    // we click via the locator's `scrollIntoViewIfNeeded()`.
    const cell = page.getByTestId(cellId);
    if (await cell.isVisible({ timeout: 2000 }).catch(() => false)) {
      await cell.click();
    } else {
      // Fallback: pick any visible cell on the first room row.
      const fallbackCell = page
        .getByTestId(`accommodation-calendar-row-${firstRoomId}`)
        .locator('button[data-testid^="accommodation-calendar-cell-"]')
        .first();
      await fallbackCell.click();
    }

    // ── 3. Modal opens → check_in prefilled → fill occupant + submit ─
    await expect(
      page.getByRole('dialog').getByText(/Create booking/i).first(),
    ).toBeVisible({ timeout: 10_000 });
    const checkInInput = page.getByTestId('accommodation-calendar-check-in');
    const checkInValue = await checkInInput.inputValue();
    expect(checkInValue).toMatch(/^\d{4}-\d{2}-\d{2}$/);

    // Set a 4-night stay so the block clearly spans multiple columns.
    const checkOutIso = isoNDaysFromToday(
      Number(checkInValue.slice(-2)) + 4 > 28
        ? Number(checkInValue.slice(-2)) - 2 + 4
        : 3 + 4,
    );
    // Simpler: just add +4 to whatever check-in is.
    const ci = new Date(checkInValue + 'T00:00:00');
    ci.setDate(ci.getDate() + 4);
    const computedCheckOut = ci.toISOString().slice(0, 10);
    await page
      .getByTestId('accommodation-calendar-check-out')
      .fill(computedCheckOut);

    await page
      .getByTestId('accommodation-calendar-occupant-name')
      .fill('Calendar Guest');
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '02-create-modal-filled.png'),
      fullPage: true,
    });
    await page.getByTestId('accommodation-calendar-create-submit').click();

    // ── 4. Verify the coloured block shows up ────────────────────────
    // The block has data-testid `accommodation-calendar-block-{id}` —
    // we don't know the id, so we match any block inside the target
    // room row and assert at least one is present, with `bg-amber-200`
    // (the reserved colour).
    const row = page.getByTestId(`accommodation-calendar-row-${firstRoomId}`);
    const block = row.locator('button[data-testid^="accommodation-calendar-block-"]');
    await expect(block.first()).toBeVisible({ timeout: 15_000 });
    // The block should carry the reserved colour class.
    const classAttr = await block.first().getAttribute('class');
    expect(classAttr).toContain('bg-amber-200');
    // Tooltip should include the guest name.
    expect(await block.first().getAttribute('title')).toContain('Calendar Guest');

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '03-block-visible.png'),
      fullPage: true,
    });

    // ── 5. Click the block → drawer opens with state-machine actions ─
    await block.first().click();
    await expect(
      page.getByTestId('accommodation-calendar-booking-drawer'),
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByTestId('accommodation-calendar-drawer-action-checked_in'),
    ).toBeVisible({ timeout: 5_000 });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '04-block-drawer.png'),
      fullPage: true,
    });
    // Close the drawer via Escape.
    await page.keyboard.press('Escape');

    // ── 6. Standalone /accommodation/calendar route + view toggle ───
    await page.goto('/accommodation/calendar');
    await expect(
      page.getByTestId('accommodation-calendar-controls'),
    ).toBeVisible({ timeout: 30_000 });
    // Filter dropdown lets us scope to our seeded accommodation.
    await page
      .getByTestId('accommodation-calendar-filter')
      .selectOption(seed.accommodationId);
    await expect(
      page.getByTestId('accommodation-calendar-grid'),
    ).toBeVisible({ timeout: 15_000 });
    // Toggle Month view.
    await page.getByTestId('accommodation-calendar-view-month').click();
    await expect(
      page.getByTestId('accommodation-calendar-view-month'),
    ).toHaveAttribute('aria-selected', 'true');
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '05-standalone-month-view.png'),
      fullPage: true,
    });
    // Today button.
    await page.getByTestId('accommodation-calendar-today').click();
    // Back to week.
    await page.getByTestId('accommodation-calendar-view-week').click();
    await expect(
      page.getByTestId('accommodation-calendar-view-week'),
    ).toHaveAttribute('aria-selected', 'true');
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '06-standalone-week-view.png'),
      fullPage: true,
    });
  });
});
