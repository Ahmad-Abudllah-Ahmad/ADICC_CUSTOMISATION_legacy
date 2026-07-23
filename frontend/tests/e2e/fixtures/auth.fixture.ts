/**
 * auth.fixture.ts — pre-authenticated browser context.
 *
 * Strategy:
 *   1. Worker-scoped fixture obtains a demo JWT exactly once per worker.
 *   2. Token is cached on disk under `playwright/.auth/demo.json` so
 *      every spec in every worker reuses it — 1000 tests don't all
 *      re-login (backend rate-limits /auth/login/ at ~5 req/min/IP).
 *   3. The fixture exposes both:
 *        - `authedPage`: a Page already authenticated (tokens injected
 *          via addInitScript so the app boots logged-in).
 *        - `accessToken`: the raw JWT (for API fixture and helpers).
 *
 * Demo creds: per MEMORY, the canonical demo user is
 *   demo@openconstructionerp.com (NOT openestimate.io — note the "r").
 */
import { test as base, type Page, type APIRequestContext } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname_esm = path.dirname(fileURLToPath(import.meta.url));
// Auth cache lives at frontend/playwright/.auth/demo.json (ignored by git).
const AUTH_DIR = path.resolve(__dirname_esm, '../../../playwright/.auth');
const AUTH_FILE = path.join(AUTH_DIR, 'demo.json');

const API_URL = process.env.OE_TEST_API_URL ?? 'http://localhost:8000';
export const DEMO_USER = {
  email: process.env.OE_TEST_DEMO_EMAIL ?? 'demo@openconstructionerp.com',
  password: process.env.OE_TEST_DEMO_PASSWORD ?? 'OpenEstimate2024!',
};

interface AuthBundle {
  accessToken: string;
  refreshToken: string;
  email: string;
  obtainedAt: number;
}

/** Read on-disk cache if fresh (<55 min — well under typical 60-min JWT exp). */
function loadCachedAuth(): AuthBundle | null {
  try {
    if (!fs.existsSync(AUTH_FILE)) return null;
    const raw = JSON.parse(fs.readFileSync(AUTH_FILE, 'utf-8')) as AuthBundle;
    const ageMin = (Date.now() - raw.obtainedAt) / 60_000;
    if (ageMin > 55) return null;
    if (!raw.accessToken) return null;
    return raw;
  } catch {
    return null;
  }
}

function persistAuth(bundle: AuthBundle): void {
  fs.mkdirSync(AUTH_DIR, { recursive: true });
  fs.writeFileSync(AUTH_FILE, JSON.stringify(bundle, null, 2), 'utf-8');
}

/**
 * Hit the backend /auth/demo-login/ (or fall back to standard /auth/login/)
 * and return tokens. Tries demo-login first because the demo account is
 * intentionally exposed without rate-limiting in dev.
 */
async function obtainTokens(
  request: APIRequestContext,
): Promise<{ access: string; refresh: string }> {
  // Preferred: demo-login (no rate-limit penalty in dev/demo env).
  const demoRes = await request.post(`${API_URL}/api/v1/users/auth/demo-login/`, {
    failOnStatusCode: false,
    data: {},
  });
  if (demoRes.ok()) {
    const body = await demoRes.json();
    return {
      access: body.access_token as string,
      refresh: (body.refresh_token ?? body.access_token) as string,
    };
  }
  // Fallback: classic credentials login.
  const loginRes = await request.post(`${API_URL}/api/v1/users/auth/login/`, {
    failOnStatusCode: false,
    data: { email: DEMO_USER.email, password: DEMO_USER.password },
  });
  if (!loginRes.ok()) {
    throw new Error(
      `auth.fixture: cannot log in (demo-login=${demoRes.status()}, ` +
        `login=${loginRes.status()}). Is backend reachable at ${API_URL}?`,
    );
  }
  const body = await loginRes.json();
  return {
    access: body.access_token as string,
    refresh: (body.refresh_token ?? body.access_token) as string,
  };
}

/** Inject tokens into localStorage+sessionStorage so the SPA boots authed. */
async function hydrateStorage(
  page: Page,
  tokens: { access: string; refresh: string; email: string },
): Promise<void> {
  await page.addInitScript((t) => {
    localStorage.setItem('oe_access_token', t.access);
    localStorage.setItem('oe_refresh_token', t.refresh);
    localStorage.setItem('oe_remember', '1');
    localStorage.setItem('oe_user_email', t.email);
    // Suppress onboarding/tour overlays which interfere with selectors.
    localStorage.setItem('oe_onboarding_completed', 'true');
    localStorage.setItem('oe_welcome_dismissed', 'true');
    localStorage.setItem('oe_tour_completed', 'true');
    sessionStorage.setItem('oe_access_token', t.access);
    sessionStorage.setItem('oe_refresh_token', t.refresh);
  }, tokens);
}

type WorkerFixtures = {
  workerAuth: AuthBundle;
  accessToken: string;
};

type TestFixtures = {
  authedPage: Page;
};

/**
 * Worker-scoped auth: one login per worker, cached on disk for cross-worker
 * reuse. Test-scoped `authedPage` opens a fresh page with tokens already
 * injected via addInitScript.
 *
 * Both `workerAuth` (full bundle) and `accessToken` (raw JWT) are
 * worker-scoped so worker-scoped consumers (e.g. seed.fixture) can depend
 * on them. Playwright forbids worker fixtures from depending on test
 * fixtures.
 */
export const test = base.extend<TestFixtures, WorkerFixtures>({
  workerAuth: [
    async ({ playwright }, use) => {
      let bundle = loadCachedAuth();
      if (!bundle) {
        const request = await playwright.request.newContext();
        try {
          const { access, refresh } = await obtainTokens(request);
          bundle = {
            accessToken: access,
            refreshToken: refresh,
            email: DEMO_USER.email,
            obtainedAt: Date.now(),
          };
          persistAuth(bundle);
        } finally {
          await request.dispose();
        }
      }
      await use(bundle);
    },
    { scope: 'worker' },
  ],

  accessToken: [
    async ({ workerAuth }, use) => {
      await use(workerAuth.accessToken);
    },
    { scope: 'worker' },
  ],

  authedPage: async ({ page, workerAuth }, use) => {
    await hydrateStorage(page, {
      access: workerAuth.accessToken,
      refresh: workerAuth.refreshToken,
      email: workerAuth.email,
    });
    await use(page);
  },
});

export { expect } from '@playwright/test';
