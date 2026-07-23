/**
 * Playwright spec for the FloatingChatButton + FloatingChatPanel.
 *
 * Captures screenshots into qa-tests/_floating-chat-<date>/ so the operator
 * can eyeball them. Tolerant of the case where the demo backend has no AI
 * provider configured (records the onboarding-state screenshot but does not
 * fail the run).
 */

import { test, expect, type Page } from '@playwright/test';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const DEMO_EMAIL = 'demo@openconstructionerp.com';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..', '..');
const TODAY = new Date().toISOString().slice(0, 10);
const SCREENSHOT_DIR = path.resolve(
  REPO_ROOT,
  'qa-tests',
  `_floating-chat-${TODAY}`,
);

function ensureDir(): void {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function demoLogin(page: Page): Promise<void> {
  const response = await page.request.post('/api/v1/users/auth/demo-login/', {
    data: { email: DEMO_EMAIL },
  });
  if (!response.ok()) {
    test.skip(true, `demo-login unavailable: ${response.status()}`);
  }
  const body = (await response.json()) as {
    access_token: string;
    refresh_token: string;
  };
  await page.goto('/');
  await page.evaluate(
    ({ access, refresh }) => {
      sessionStorage.setItem('oe_access_token', access);
      sessionStorage.setItem('oe_refresh_token', refresh);
    },
    { access: body.access_token, refresh: body.refresh_token },
  );
  // Soft-reload so the auth store picks up the seeded tokens and the
  // floating chat button becomes eligible to render.
  await page.goto('/');
  // Dismiss any onboarding tour if present so it doesn't block clicks.
  const skip = page.getByRole('button', { name: /skip/i }).first();
  if (await skip.isVisible().catch(() => false)) {
    await skip.click().catch(() => {});
  }
}

test.describe('Floating chat widget', () => {
  test('button appears, panel opens, full-page link navigates, panel hides on /chat', async ({
    page,
  }) => {
    ensureDir();
    await demoLogin(page);

    // 1. Button visible on the dashboard.
    const button = page.locator('[data-testid="floating-chat-button"]');
    await expect(button).toBeVisible({ timeout: 15_000 });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '01-button-visible.png'),
      fullPage: false,
    });

    // 2. Click the button → panel slides in.
    await button.click();
    const panel = page.locator('[data-testid="floating-chat-panel"]');
    await expect(panel).toBeVisible({ timeout: 5_000 });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '02-panel-open.png'),
      fullPage: false,
    });

    // 3. Send a "list my projects" prompt.
    const input = page.locator('[data-testid="floating-chat-input"]');
    await expect(input).toBeVisible();
    await input.fill('list my projects');
    await input.press('Enter');

    // Wait either for a tool-result renderer OR for the onboarding/error
    // text to appear. We intentionally don't fail the whole test if the
    // backend lacks an AI key — that's a deploy-state issue, not a UI bug.
    const userMsgVisible = await page
      .getByText('list my projects', { exact: true })
      .first()
      .isVisible({ timeout: 5_000 })
      .catch(() => false);
    expect(userMsgVisible).toBe(true);

    // Give the stream a moment to either render a renderer OR fail.
    await page.waitForTimeout(6_000);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '03-after-prompt.png'),
      fullPage: false,
    });

    // 4. Click "Open full page" → navigates to /chat and panel hides itself.
    const openFull = page.locator('[data-testid="floating-chat-open-full"]');
    await openFull.click();
    await page.waitForURL(/\/chat(\/|$)/, { timeout: 10_000 });
    // On /chat the floating button should be hidden (no duplication).
    const onChatButton = page.locator('[data-testid="floating-chat-button"]');
    await expect(onChatButton).toHaveCount(0, { timeout: 5_000 });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '04-on-chat-route-button-hidden.png'),
      fullPage: false,
    });

    // 5. Navigate to /projects → button visible again.
    await page.goto('/projects');
    await expect(
      page.locator('[data-testid="floating-chat-button"]'),
    ).toBeVisible({ timeout: 10_000 });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '05-on-projects-button-visible.png'),
      fullPage: false,
    });
  });

  test('mobile viewport renders panel full-width', async ({ browser }) => {
    ensureDir();
    const ctx = await browser.newContext({ viewport: { width: 375, height: 720 } });
    const page = await ctx.newPage();
    await demoLogin(page);
    const button = page.locator('[data-testid="floating-chat-button"]');
    await expect(button).toBeVisible({ timeout: 15_000 });
    await button.click();
    const panel = page.locator('[data-testid="floating-chat-panel"]');
    await expect(panel).toBeVisible({ timeout: 5_000 });
    // On mobile the panel should occupy the viewport horizontally
    // (w-full + h-full classes).
    const box = await panel.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.width).toBeGreaterThan(370);
    }
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '06-mobile-panel-fullscreen.png'),
      fullPage: false,
    });
    await ctx.close();
  });
});
