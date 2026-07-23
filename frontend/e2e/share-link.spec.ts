/**
 * E2E test — password-protected share links.
 *
 * Mirror of frontend/tests/e2e/share-link.spec.ts at the path the
 * Playwright config actually scans. See the canonical spec for the
 * flow description.
 */

import { test, expect, type BrowserContext } from '@playwright/test';
import { login } from './helpers';
import path from 'path';
import fs from 'fs';

const SCREENSHOT_DIR = path.resolve(__dirname, '..', 'tests', 'e2e', 'screenshots');
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

const SHARE_PASSWORD = 'testpw';
const WRONG_PASSWORD = 'wrongpw';

test.describe('Password-protected share links', () => {
  test('owner mints a share link, recipient unlocks it', async ({
    page,
    browser,
  }: {
    page: Awaited<ReturnType<BrowserContext['newPage']>>;
    browser: BrowserContext['browser'];
  }) => {
    await login(page);
    await page.goto('/files');
    await page.waitForLoadState('networkidle');

    const docsCard = page.getByRole('button', { name: /Documents/i }).first();
    if (await docsCard.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await docsCard.click();
      await page.waitForLoadState('networkidle');
    }

    const firstRow = page
      .locator('[data-kind="document"], tr[data-id], [data-testid="file-row"]')
      .first();
    if (!(await firstRow.isVisible({ timeout: 5_000 }).catch(() => false))) {
      test.skip(true, 'No documents available in this environment.');
      return;
    }
    await firstRow.click();

    const shareButton = page.getByTestId('file-share-button');
    await expect(shareButton).toBeVisible({ timeout: 10_000 });
    await shareButton.click();

    const passwordInput = page.getByLabel(/password.*optional/i);
    await passwordInput.fill(SHARE_PASSWORD);
    await page.getByRole('radio', { name: /7 days/i }).click();

    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'share-modal.png') });

    const createBtn = page.getByRole('button', { name: /create link/i });
    await createBtn.click();

    const urlBlock = page.getByTestId('share-link-url');
    await expect(urlBlock).toBeVisible({ timeout: 10_000 });
    const shareUrl = (await urlBlock.textContent())?.trim() ?? '';
    expect(shareUrl).toMatch(/\/share\/[A-Za-z0-9_-]{20,}/);

    const incognito = await browser!.newContext();
    const guestPage = await incognito.newPage();
    const shareUrlPath = shareUrl.replace(/^https?:\/\/[^/]+/, '');
    await guestPage.goto(shareUrlPath);

    const passwordPromptInput = guestPage.getByTestId('share-password-input');
    await expect(passwordPromptInput).toBeVisible({ timeout: 15_000 });
    await guestPage.screenshot({
      path: path.join(SCREENSHOT_DIR, 'share-password-prompt.png'),
    });

    await passwordPromptInput.fill(WRONG_PASSWORD);
    await guestPage.getByTestId('share-unlock-button').click();
    await expect(guestPage.getByTestId('share-error')).toBeVisible({ timeout: 10_000 });

    await passwordPromptInput.fill(SHARE_PASSWORD);
    await guestPage.getByTestId('share-unlock-button').click();
    const downloadLink = guestPage.getByTestId('share-download-link');
    await expect(downloadLink).toBeVisible({ timeout: 15_000 });
    await guestPage.screenshot({
      path: path.join(SCREENSHOT_DIR, 'share-success.png'),
    });
    const href = await downloadLink.getAttribute('href');
    expect(href).toContain('/file/');

    await incognito.close();
  });
});
