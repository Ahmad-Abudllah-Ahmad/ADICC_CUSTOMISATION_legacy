/**
 * E2E test — password-protected share links.
 *
 * Flow:
 *   1. Owner logs in, opens File Manager, focuses a Document row.
 *   2. Clicks the new "Share" button in the preview pane.
 *   3. Enters a password ("testpw"), selects 7-day expiry, clicks
 *      "Create link", copies the URL.
 *   4. Opens the URL in an incognito context (no auth):
 *        a. Wrong password → inline error.
 *        b. Right password → download link rendered.
 *
 * Screenshots are written next to the spec under ``screenshots/`` so
 * they can be diffed in PRs.
 *
 * NOTE: This spec lives in ``frontend/tests/e2e/`` per the feature
 * request. The Playwright config currently scans ``./e2e``; an
 * identical copy is therefore mirrored to ``frontend/e2e/`` (see
 * ``frontend/e2e/share-link.spec.ts``) so it runs without changing
 * ``playwright.config.ts``.
 */

import { test, expect, type BrowserContext } from '@playwright/test';
import { login } from '../../e2e/helpers';
import path from 'path';
import fs from 'fs';

const SCREENSHOT_DIR = path.resolve(__dirname, 'screenshots');
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
    // ── 1. Owner: log in and navigate to /files ────────────────────────
    await login(page);
    await page.goto('/files');
    // The File Manager page mounts a tree + grid; wait for it to settle.
    await page.waitForLoadState('networkidle');

    // Try to drill into Documents category if the folder grid is showing.
    const docsCard = page.getByRole('button', { name: /Documents/i }).first();
    if (await docsCard.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await docsCard.click();
      await page.waitForLoadState('networkidle');
    }

    // Pick the first document row in either grid or list view. If no
    // documents exist, skip with a clear message — the rest of the spec
    // depends on having one.
    const firstRow = page.locator('[data-kind="document"], tr[data-id], [data-testid="file-row"]').first();
    if (!(await firstRow.isVisible({ timeout: 5_000 }).catch(() => false))) {
      test.skip(true, 'No documents available in this environment; cannot exercise share flow.');
      return;
    }
    await firstRow.click();

    // Preview pane should appear with the Share button.
    const shareButton = page.getByTestId('file-share-button');
    await expect(shareButton).toBeVisible({ timeout: 10_000 });
    await shareButton.click();

    // ── 2. Modal: enter password + set expiry + create ────────────────
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

    // ── 3. Recipient: open the URL in an incognito context ────────────
    const incognito = await browser!.newContext();
    const guestPage = await incognito.newPage();
    // ``shareUrl`` is absolute (window.origin prefixed) — strip the host
    // so we hit the dev server via baseURL.
    const shareUrlPath = shareUrl.replace(/^https?:\/\/[^/]+/, '');
    await guestPage.goto(shareUrlPath);

    // Password prompt visible.
    const passwordPromptInput = guestPage.getByTestId('share-password-input');
    await expect(passwordPromptInput).toBeVisible({ timeout: 15_000 });
    await guestPage.screenshot({
      path: path.join(SCREENSHOT_DIR, 'share-password-prompt.png'),
    });

    // ── 4a. Wrong password → inline error ─────────────────────────────
    await passwordPromptInput.fill(WRONG_PASSWORD);
    await guestPage.getByTestId('share-unlock-button').click();
    await expect(guestPage.getByTestId('share-error')).toBeVisible({
      timeout: 10_000,
    });

    // ── 4b. Right password → download link rendered ───────────────────
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
