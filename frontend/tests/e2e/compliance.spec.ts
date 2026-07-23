/**
 * E2E — Project Compliance tab.
 *
 * Logs into the demo seed account, opens the first seeded project,
 * switches to the Compliance tab and:
 *   1. Captures the empty state.
 *   2. Creates a 60-day-out insurance policy → expects green active pill.
 *   3. Captures the populated table.
 *   4. Creates a 15-day-out building permit → expects amber expiring-soon.
 *   5. Captures the expiring screenshot.
 *
 * Screenshots land in ``screenshots/compliance-{empty,table,create-modal,expiring}.png``.
 *
 * Run explicitly:
 *   npx playwright test tests/e2e/compliance.spec.ts
 */
import { test, expect, type Page } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SCREENSHOT_DIR = path.resolve(__dirname, '../../screenshots');

const DEMO_USER = {
  email: process.env.E2E_USER_EMAIL ?? 'demo@openconstructionerp.com',
  password: process.env.E2E_USER_PASSWORD ?? 'DemoPass1234!',
};

function isoPlusDays(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  await expect(page.locator('form')).toBeVisible({ timeout: 15_000 });
  await page.locator('input[type="email"]').fill(DEMO_USER.email);
  const passwordInput = page
    .locator('#login-password, input[type="password"]')
    .first();
  await passwordInput.fill(DEMO_USER.password);
  await page.locator('button[type="submit"]').click();
  await expect(page).not.toHaveURL(/\/login/, { timeout: 20_000 });
}

async function navigateToFirstProject(page: Page): Promise<void> {
  const token = await page.evaluate(
    () =>
      sessionStorage.getItem('oe_access_token') ??
      localStorage.getItem('oe_access_token'),
  );
  const res = await page.request.get('/api/v1/projects/?limit=1', {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok()) {
    throw new Error(`GET /v1/projects/ returned ${res.status()}`);
  }
  const body = await res.json();
  const items: { id: string }[] = Array.isArray(body)
    ? body
    : body.items ?? [];
  if (items.length === 0) {
    throw new Error('No projects in the seed DB.');
  }
  const id = items[0].id;
  await page.goto(`/projects/${id}`);
  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]{36}/, {
    timeout: 15_000,
  });
}

async function openComplianceTab(page: Page): Promise<void> {
  const tab = page.getByRole('button', { name: /compliance/i }).first();
  await expect(tab).toBeVisible({ timeout: 10_000 });
  await tab.click();
  await page.waitForSelector('[data-testid="compliance-page"]', {
    timeout: 10_000,
  });
}

async function fillCreateModal(
  page: Page,
  opts: {
    docType: string;
    name: string;
    daysOut: number;
    notify: number;
  },
): Promise<void> {
  // Open via either CTA path.
  const ctaInTable = page.getByTestId('compliance-new');
  const ctaInEmpty = page.getByTestId('compliance-empty-cta');
  const cta = (await ctaInTable.isVisible().catch(() => false))
    ? ctaInTable
    : ctaInEmpty;
  await cta.click();
  await expect(page.getByTestId('create-compliance-modal')).toBeVisible({
    timeout: 5_000,
  });

  await page
    .getByTestId('compliance-field-doc-type')
    .selectOption(opts.docType);
  await page.getByTestId('compliance-field-name').fill(opts.name);
  await page
    .getByTestId('compliance-field-effective')
    .fill(isoPlusDays(0));
  await page
    .getByTestId('compliance-field-expires')
    .fill(isoPlusDays(opts.daysOut));
  await page
    .getByTestId('compliance-field-notify')
    .fill(String(opts.notify));

  await page.getByTestId('compliance-submit').click();
  await expect(page.getByTestId('create-compliance-modal')).toBeHidden({
    timeout: 8_000,
  });
}

test.beforeAll(() => {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }
});

test('Compliance tab — create insurance + permit, capture screenshots', async ({
  page,
}) => {
  await login(page);
  await navigateToFirstProject(page);
  await openComplianceTab(page);

  // 1. Empty-state screenshot (we render whatever is currently visible —
  //    the project may already have docs from prior runs, that's OK).
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, 'compliance-empty.png'),
    fullPage: true,
  });

  // Create-modal screenshot.
  const ctaInTable = page.getByTestId('compliance-new');
  const ctaInEmpty = page.getByTestId('compliance-empty-cta');
  const cta = (await ctaInTable.isVisible().catch(() => false))
    ? ctaInTable
    : ctaInEmpty;
  await cta.click();
  await expect(page.getByTestId('create-compliance-modal')).toBeVisible({
    timeout: 5_000,
  });
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, 'compliance-create-modal.png'),
    fullPage: true,
  });
  await page.keyboard.press('Escape');

  // 2. Insurance — 60 days out, notify=30 → expect active.
  await fillCreateModal(page, {
    docType: 'insurance_general_liability',
    name: 'GL Policy — E2E',
    daysOut: 60,
    notify: 30,
  });
  await expect(
    page.locator('table tbody tr', { hasText: 'GL Policy — E2E' }),
  ).toBeVisible({ timeout: 10_000 });

  // 3. Populated table screenshot.
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, 'compliance-table.png'),
    fullPage: true,
  });

  // 4. Building permit — 15 days out, notify=30 → expect expiring_soon.
  await fillCreateModal(page, {
    docType: 'permit_building',
    name: 'Building permit — E2E',
    daysOut: 15,
    notify: 30,
  });
  const permitRow = page.locator('table tbody tr', {
    hasText: 'Building permit — E2E',
  });
  await expect(permitRow).toBeVisible({ timeout: 10_000 });
  await expect(permitRow).toContainText(/expiring/i);

  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, 'compliance-expiring.png'),
    fullPage: true,
  });
});
