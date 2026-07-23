/**
 * E2E — Floating chat onboarding polish.
 *
 * Verifies the three features added in this iteration:
 *   1. Proactive "Configure AI" banner appears on panel open when no AI
 *      provider is configured; the "Skip" button hides it for this session.
 *   2. Page-contextual suggestion chips render ABOVE the 6 generic chips on
 *      pages we have a context bundle for (/boq/:id, /accommodation/:id).
 *   3. Clicking a contextual chip auto-sends it as a user message.
 *
 * Screenshots land in qa-tests/_floating-chat-onboarding-2026-05-24/.
 *
 * Run explicitly:
 *   npx playwright test e2e/floating-chat-onboarding.spec.ts
 */
import { test, expect, type Page } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SCREENSHOT_DIR = path.resolve(
  __dirname,
  '../../qa-tests/_floating-chat-onboarding-2026-05-24',
);

const DEMO_USER = {
  email: process.env.E2E_USER_EMAIL ?? 'demo@openconstructionerp.com',
};

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

async function suppressTours(page: Page): Promise<void> {
  await page.addInitScript(() => {
    try {
      localStorage.setItem('oe.tour_completed', 'true');
      localStorage.setItem('oe_tour_completed', 'true');
    } catch {
      /* ignore */
    }
  });
}

/**
 * Force the panel into the "no AI configured" branch by intercepting the
 * settings call. This keeps the test deterministic regardless of which
 * provider keys happen to be set in the local dev DB.
 */
async function mockNoAIConfigured(page: Page): Promise<void> {
  await page.route('**/api/v1/ai/settings/', (route) => {
    void route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'mock',
        user_id: 'mock',
        anthropic_api_key_set: false,
        openai_api_key_set: false,
        gemini_api_key_set: false,
        openrouter_api_key_set: false,
        mistral_api_key_set: false,
        groq_api_key_set: false,
        deepseek_api_key_set: false,
        together_api_key_set: false,
        fireworks_api_key_set: false,
        perplexity_api_key_set: false,
        cohere_api_key_set: false,
        ai21_api_key_set: false,
        xai_api_key_set: false,
        zhipu_api_key_set: false,
        baidu_api_key_set: false,
        yandex_api_key_set: false,
        gigachat_api_key_set: false,
        preferred_model: '',
        model_overrides: {},
        default_models: {},
        metadata_: {},
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      }),
    });
  });
}

test.beforeAll(() => {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }
});

test.describe('Floating chat onboarding polish', () => {
  test.setTimeout(180_000);

  test('no AI banner appears on / and can be dismissed for the session', async ({
    page,
  }) => {
    await suppressTours(page);
    await mockNoAIConfigured(page);
    await login(page);

    // Open the chat panel.
    await expect(page.getByTestId('floating-chat-button')).toBeVisible({
      timeout: 30_000,
    });
    await page.getByTestId('floating-chat-button').click();
    await expect(page.getByTestId('floating-chat-panel')).toBeVisible({
      timeout: 10_000,
    });

    // The "Configure AI" banner is visible above the input.
    const banner = page.getByTestId('floating-chat-no-ai-banner');
    await expect(banner).toBeVisible({ timeout: 10_000 });
    await expect(banner).toHaveAttribute('role', 'alert');
    await expect(
      page.getByTestId('floating-chat-no-ai-configure'),
    ).toBeVisible();
    await expect(page.getByTestId('floating-chat-no-ai-skip')).toBeVisible();
    await page.waitForTimeout(300);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '01-no-ai-banner-on-home.png'),
      fullPage: true,
    });

    // Click Skip → banner disappears for this session.
    await page.getByTestId('floating-chat-no-ai-skip').click();
    await expect(banner).toBeHidden({ timeout: 5_000 });

    // Close + reopen the panel — banner should STAY hidden because the
    // session flag persists on the zustand store (not localStorage).
    await page.getByTestId('floating-chat-close').click();
    await expect(page.getByTestId('floating-chat-panel')).toBeHidden();
    await page.getByTestId('floating-chat-button').click();
    await expect(page.getByTestId('floating-chat-panel')).toBeVisible();
    await expect(
      page.getByTestId('floating-chat-no-ai-banner'),
    ).toBeHidden({ timeout: 3_000 });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '02-banner-dismissed-after-skip.png'),
      fullPage: true,
    });
  });

  test('contextual chips render above generic chips on /boq/:id', async ({
    page,
  }) => {
    await suppressTours(page);
    await mockNoAIConfigured(page);
    await login(page);

    // Find a BOQ to navigate to. The BOQ list endpoint is project-scoped,
    // so first fetch a project, then ask for its BOQs.
    const token = await page.evaluate(() =>
      sessionStorage.getItem('oe_access_token'),
    );
    const authHeader = { Authorization: `Bearer ${token}` };

    const projRes = await page.request.get('/api/v1/projects/', {
      headers: authHeader,
    });
    if (!projRes.ok()) {
      test.skip(true, `Projects list endpoint returned ${projRes.status()}`);
    }
    const projBody = (await projRes.json()) as {
      items?: { id: string }[];
      results?: { id: string }[];
    } | { id: string }[];
    const projects = Array.isArray(projBody)
      ? projBody
      : projBody.items ?? projBody.results ?? [];
    if (projects.length === 0) {
      test.skip(true, 'No projects in seed DB');
    }

    // Walk projects until we find one with at least one BOQ.
    let boqId: string | null = null;
    for (const p of projects.slice(0, 10)) {
      const boqRes = await page.request.get(
        `/api/v1/boq/boqs/?project_id=${p.id}`,
        { headers: authHeader },
      );
      if (!boqRes.ok()) continue;
      const list = (await boqRes.json()) as { id: string }[];
      if (Array.isArray(list) && list.length > 0) {
        boqId = list[0]!.id;
        break;
      }
    }
    if (!boqId) {
      test.skip(true, 'No BOQs found across first 10 projects');
    }

    await page.goto(`/boq/${boqId}`);
    // The page should render — we don't assert on its internals, just that
    // we got past the loading splash.
    await page.waitForLoadState('networkidle', { timeout: 30_000 });

    // Open chat.
    await expect(page.getByTestId('floating-chat-button')).toBeVisible({
      timeout: 30_000,
    });
    await page.getByTestId('floating-chat-button').click();
    await expect(page.getByTestId('floating-chat-panel')).toBeVisible();

    // Contextual chips appear ABOVE the generic ones — assert both labels
    // are visible and the contextual chip group renders.
    await expect(
      page.getByTestId('floating-chat-contextual-label'),
    ).toBeVisible({ timeout: 5_000 });
    await expect(
      page.getByTestId('floating-chat-contextual-chips'),
    ).toBeVisible();

    // 3 contextual chips for /boq/:id.
    await expect(
      page.getByTestId('floating-chat-suggestion-ctx-0'),
    ).toBeVisible();
    await expect(
      page.getByTestId('floating-chat-suggestion-ctx-1'),
    ).toBeVisible();
    await expect(
      page.getByTestId('floating-chat-suggestion-ctx-2'),
    ).toBeVisible();

    // 6 generic chips still visible.
    await expect(
      page.getByTestId('floating-chat-suggestion-generic-0'),
    ).toBeVisible();
    await expect(
      page.getByTestId('floating-chat-suggestion-generic-5'),
    ).toBeVisible();

    // DOM order: the contextual label should come before the generic label
    // in document order.
    const ctxLabelY = await page
      .getByTestId('floating-chat-contextual-label')
      .evaluate((el) => el.getBoundingClientRect().top);
    const genericChip0Y = await page
      .getByTestId('floating-chat-suggestion-generic-0')
      .evaluate((el) => el.getBoundingClientRect().top);
    expect(ctxLabelY).toBeLessThan(genericChip0Y);

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '03-boq-contextual-chips.png'),
      fullPage: true,
    });

    // Click a contextual chip — it should auto-send (the message thread
    // replaces the empty state).
    const ctxChip0 = page.getByTestId('floating-chat-suggestion-ctx-0');
    const chipText = (await ctxChip0.textContent())?.trim() ?? '';
    expect(chipText.length).toBeGreaterThan(0);
    await ctxChip0.click();

    // The chip text should now appear as a user message bubble.
    await expect(page.getByText(chipText, { exact: false }).first()).toBeVisible({
      timeout: 5_000,
    });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '04-boq-after-chip-click.png'),
      fullPage: true,
    });
  });

  test('contextual chips switch when navigating to /accommodation/:id', async ({
    page,
  }) => {
    await suppressTours(page);
    await mockNoAIConfigured(page);
    await login(page);

    // Try to find an accommodation. Skip if none in seed.
    const token = await page.evaluate(() =>
      sessionStorage.getItem('oe_access_token'),
    );
    const accRes = await page.request.get('/api/v1/accommodation/', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!accRes.ok()) {
      test.skip(true, `Accommodation list endpoint returned ${accRes.status()}`);
    }
    const accBody = (await accRes.json()) as
      | { items?: { id: string }[]; results?: { id: string }[] }
      | { id: string }[];
    const items = Array.isArray(accBody)
      ? accBody
      : accBody.items ?? accBody.results ?? [];
    if (items.length === 0) {
      test.skip(true, 'No accommodations in seed DB');
    }
    const accId = items[0]!.id;

    await page.goto(`/accommodation/${accId}`);
    await page.waitForLoadState('networkidle', { timeout: 30_000 });

    await page.getByTestId('floating-chat-button').click();
    await expect(page.getByTestId('floating-chat-panel')).toBeVisible();

    await expect(
      page.getByTestId('floating-chat-contextual-label'),
    ).toBeVisible();
    // Accommodation has 3 contextual chips.
    await expect(
      page.getByTestId('floating-chat-suggestion-ctx-0'),
    ).toBeVisible();
    await expect(
      page.getByTestId('floating-chat-suggestion-ctx-1'),
    ).toBeVisible();
    await expect(
      page.getByTestId('floating-chat-suggestion-ctx-2'),
    ).toBeVisible();

    // The chip text must be DIFFERENT from the /boq chips — sanity check
    // that we're really pulling from the accommodation bundle.
    const ctx0Text =
      (await page.getByTestId('floating-chat-suggestion-ctx-0').textContent()) ?? '';
    expect(ctx0Text).toMatch(/occupancy|trend|Belegung|заселен/i);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '05-accommodation-contextual-chips.png'),
      fullPage: true,
    });
  });
});
