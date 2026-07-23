/**
 * E2E — Accommodation bookings list + state-machine actions.
 *
 * Flow:
 *   1. Demo-login → create accommodation "Polish QA" with 3 rooms (API)
 *   2. Seed 4 bookings across the rooms (API)
 *   3. Navigate to detail → Bookings tab → assert 4 rows visible
 *   4. Click a reserved booking → Check in → assert status flips
 *   5. Click Check out → confirm → assert status flips
 *   6. Click filter pill "Cancelled" → assert empty
 *
 * Screenshots land in qa-tests/_accommodation-bookings-2026-05-24/.
 */
import { test, expect, type Page, type APIRequestContext } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SCREENSHOT_DIR = path.resolve(
  __dirname,
  '../../qa-tests/_accommodation-bookings-2026-05-24',
);

const DEMO_USER = {
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
  bookingIds: string[];
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
      name: `Polish QA ${Date.now()}`,
      kind: 'worker_camp',
    },
  });
  if (!accomResp.ok()) {
    throw new Error(`Create accommodation failed ${accomResp.status()}`);
  }
  const accomId = (await accomResp.json()).id as string;

  // 3 rooms.
  const labels = ['PQ-1', 'PQ-2', 'PQ-3'];
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

  // 4 bookings across the 3 rooms — 2 reserved, 1 checked_in, 1 reserved.
  // We want all in the "active" set so the default filter shows them.
  const bookingPayloads = [
    {
      room: roomIds[0],
      payload: {
        occupant_name: 'Alice Operator',
        check_in: '2026-06-01',
        check_out: '2026-06-15',
        status: 'reserved',
      },
    },
    {
      room: roomIds[0],
      payload: {
        occupant_name: 'Bob Foreman',
        check_in: '2026-07-01',
        check_out: '2026-07-15',
        status: 'reserved',
      },
    },
    {
      room: roomIds[1],
      payload: {
        occupant_name: 'Carla Welder',
        check_in: '2026-06-10',
        check_out: '2026-06-20',
        status: 'checked_in',
      },
    },
    {
      room: roomIds[2],
      payload: {
        occupant_name: 'Dan Surveyor',
        check_in: '2026-08-01',
        check_out: '2026-08-10',
        status: 'reserved',
      },
    },
  ];

  const bookingIds: string[] = [];
  for (const { room, payload } of bookingPayloads) {
    const resp = await api.post(
      `/api/v1/accommodation/rooms/${room}/bookings`,
      { headers: auth, data: payload },
    );
    if (!resp.ok()) {
      throw new Error(`Create booking failed ${resp.status()}`);
    }
    bookingIds.push((await resp.json()).id as string);
  }

  return { accommodationId: accomId, roomIds, bookingIds };
}

test.beforeAll(() => {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }
});

test.describe('Accommodation — bookings list + state machine', () => {
  test.setTimeout(240_000);

  test('list 4 bookings → check-in → check-out → filter Cancelled empty', async ({
    page,
    request,
  }) => {
    await suppressTours(page);
    const token = await login(page);

    const projectId = await firstProjectId(request, token);
    const seed = await seedAccommodation(request, token, projectId);

    // Navigate to detail → Bookings tab.
    await page.goto(`/accommodation/${seed.accommodationId}`);
    await expect(
      page.getByTestId('accommodation-detail-header'),
    ).toBeVisible({ timeout: 30_000 });

    await page.getByTestId('accommodation-detail-tab-bookings').click();
    await expect(
      page.getByTestId('accommodation-tab-panel-bookings'),
    ).toBeVisible({ timeout: 10_000 });

    // Assert 4 rows present (responsive table OR cards). On the desktop
    // viewport Playwright uses by default (1280×720) the table is shown,
    // so each booking has `booking-row-<id>`.
    for (const id of seed.bookingIds) {
      await expect(
        page.getByTestId(`booking-row-${id}`),
      ).toBeVisible({ timeout: 10_000 });
    }
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '01-bookings-list.png'),
      fullPage: true,
    });

    // Find the first reserved booking (deterministic — bookingIds[0] is
    // reserved per seed layout) and check it in.
    const firstReservedId = seed.bookingIds[0];
    await page.getByTestId(`booking-actions-${firstReservedId}`).click();
    await expect(
      page.getByTestId(`booking-actions-menu-${firstReservedId}`),
    ).toBeVisible({ timeout: 5_000 });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '02-action-menu-open.png'),
      fullPage: true,
    });
    // Check-in is reversible → no confirm dialog, fires immediately.
    await page.getByTestId(`booking-action-checked_in-${firstReservedId}`).click();
    // Badge should flip to checked_in. React Query refetch on success.
    await expect(
      page.getByTestId(`booking-status-${firstReservedId}`),
    ).toHaveText(/Checked in/i, { timeout: 10_000 });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '03-after-checkin.png'),
      fullPage: true,
    });

    // Now Check out — destructive → ConfirmDialog appears.
    await page.getByTestId(`booking-actions-${firstReservedId}`).click();
    await expect(
      page.getByTestId(`booking-actions-menu-${firstReservedId}`),
    ).toBeVisible({ timeout: 5_000 });
    await page.getByTestId(`booking-action-checked_out-${firstReservedId}`).click();
    // ConfirmDialog — pick the primary confirm button (label = "Check out").
    const confirmBtn = page.getByRole('button', { name: /^Check out$/i }).last();
    await expect(confirmBtn).toBeVisible({ timeout: 5_000 });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '04-checkout-confirm.png'),
      fullPage: true,
    });
    await confirmBtn.click();
    await expect(
      page.getByTestId(`booking-status-${firstReservedId}`),
    ).toHaveText(/Checked out/i, { timeout: 10_000 });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '05-after-checkout.png'),
      fullPage: true,
    });

    // Filter pill: Cancelled → none of the seeded bookings are cancelled,
    // so the list must be empty.
    await page.getByTestId('bookings-filter-cancelled').click();
    await expect(
      page.getByTestId('bookings-empty'),
    ).toBeVisible({ timeout: 10_000 });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '06-filter-cancelled-empty.png'),
      fullPage: true,
    });
  });
});
