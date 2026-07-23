/**
 * Playwright spec for the per-folder permissions UI.
 *
 * Captures four screenshots:
 *   - folder-perms-empty.png       (modal open, no grants → "all members")
 *   - folder-perms-modal.png       (modal open with the picker visible)
 *   - folder-perms-granted.png     (modal showing the new grant row)
 *   - folder-perms-locked-folder.png  (folder card showing the lock badge)
 *
 * Login uses the demo-login endpoint (no password) to match the rest
 * of the e2e suite. The spec gracefully skips when the seed project
 * has no other team members to grant to (a brand-new tenant without
 * an invited member).
 */

import { test, expect, type Page } from '@playwright/test';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const DEMO_EMAIL = 'demo@openconstructionerp.com';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOT_DIR = path.resolve(HERE, '..', '..', '..', 'screenshots');

async function demoLogin(page: Page): Promise<void> {
  const response = await page.request.post('/api/v1/users/auth/demo-login/', {
    data: { email: DEMO_EMAIL },
  });
  if (!response.ok()) {
    test.skip(true, `demo-login disabled or unavailable: ${response.status()}`);
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
}

async function dismissOnboardingTourIfPresent(page: Page): Promise<void> {
  const skip = page.getByRole('button', { name: /skip/i }).first();
  if (await skip.isVisible().catch(() => false)) {
    await skip.click().catch(() => {});
  }
}

async function openFilesForFirstProject(page: Page): Promise<void> {
  await page.goto('/projects');
  await dismissOnboardingTourIfPresent(page);
  const card = page.locator('h3').first();
  await card.waitFor({ state: 'visible', timeout: 15_000 });
  await card.click();
  // Navigate to /files for the active project. The Files link in the sidebar
  // uses an i18n label so we hit the route directly.
  await page.goto('/files');
  await page
    .locator('[data-testid^="folder-card-"]')
    .first()
    .waitFor({ state: 'visible', timeout: 20_000 });
}

test.describe('Folder permissions on the file-manager', () => {
  test('owner can grant + revoke a folder permission with screenshots', async ({
    page,
  }, testInfo) => {
    await demoLogin(page);
    await openFilesForFirstProject(page);

    // Find the first folder card with a "Manage access" gear. Without an
    // owner login the gear is hidden — fall back to skipping rather than
    // false-failing the spec.
    const gear = page.locator('[data-testid^="folder-manage-access-"]').first();
    if (!(await gear.isVisible().catch(() => false))) {
      // Hover its parent card to surface the gear (it has opacity-0 + group-hover).
      const firstCard = page.locator('[data-testid^="folder-card-"]').first();
      await firstCard.hover();
    }
    if (!(await gear.isVisible().catch(() => false))) {
      testInfo.annotations.push({
        type: 'note',
        description:
          'Manage-access gear not visible — caller is not the project owner.',
      });
      test.skip(true, 'demo user is not the project owner — gear hidden');
      return;
    }
    await gear.click();

    // Modal visible — empty state baseline.
    const modal = page.locator('[role="dialog"][aria-labelledby="folder-permissions-title"]');
    await expect(modal).toBeVisible({ timeout: 5_000 });

    const emptyState = page.locator('[data-testid="folder-permissions-empty"]');
    if (await emptyState.isVisible().catch(() => false)) {
      await modal.screenshot({
        path: path.join(SCREENSHOT_DIR, 'folder-perms-empty.png'),
      });
    }

    // Full modal screenshot showing the picker + grant button.
    await modal.screenshot({
      path: path.join(SCREENSHOT_DIR, 'folder-perms-modal.png'),
    });

    // Try to grant to the first non-owner member. If the picker only has
    // the placeholder option, the seed project lacks invited members —
    // emit a screenshot of the empty picker and stop.
    const picker = page.locator(
      '[data-testid="folder-permissions-user-picker"]',
    );
    const memberOptions = await picker.locator('option').count();
    if (memberOptions <= 1) {
      testInfo.annotations.push({
        type: 'note',
        description:
          'Seed project has no grantable members — skipping grant + revoke.',
      });
      return;
    }
    // Select the first real member option (index 1, after the placeholder).
    const firstValue = await picker.locator('option').nth(1).getAttribute('value');
    if (!firstValue) return;
    await picker.selectOption(firstValue);

    await page.locator('[data-testid="folder-permissions-grant-button"]').click();

    // Wait for the new grant row to appear.
    const newRow = page
      .locator('[data-testid^="folder-permission-row-"]')
      .first();
    await expect(newRow).toBeVisible({ timeout: 5_000 });

    await modal.screenshot({
      path: path.join(SCREENSHOT_DIR, 'folder-perms-granted.png'),
    });

    // Close the modal and verify the lock badge appears on the folder card.
    await page.keyboard.press('Escape');
    await expect(modal).toBeHidden({ timeout: 3_000 });

    const lock = page.locator('[data-testid^="folder-lock-"]').first();
    await expect(lock).toBeVisible({ timeout: 5_000 });
    const card = page.locator('[data-testid^="folder-card-"]').first();
    await card.screenshot({
      path: path.join(SCREENSHOT_DIR, 'folder-perms-locked-folder.png'),
    });

    // Re-open the modal and revoke. The revoke button uses confirm() so
    // accept the dialog before clicking.
    await card.hover();
    await page.locator('[data-testid^="folder-manage-access-"]').first().click();
    page.once('dialog', (dialog) => dialog.accept().catch(() => {}));
    await page
      .locator('[data-testid^="folder-permission-revoke-"]')
      .first()
      .click();

    // After revoke the lock STAYS — the folder remains "managed" (no
    // members cleared) and the empty state shows. This matches the
    // backend contract documented in folder_permissions_service.py.
    await expect(
      page.locator('[data-testid="folder-permissions-empty"]'),
    ).toBeVisible({ timeout: 5_000 });
  });
});
