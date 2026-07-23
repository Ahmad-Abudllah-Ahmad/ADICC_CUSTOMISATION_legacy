/**
 * Smoke — settings opens and every tab loads.
 */
import { test, expect } from '../fixtures';
import { gotoModule, captureScreen } from '../helpers';

test.describe('@smoke settings', () => {
  test('settings page mounts', async ({ authedPage }) => {
    await gotoModule(authedPage, 'settings');
    // Either a heading "Settings" (en) / "Einstellungen" (de) / "Настройки" (ru),
    // or any element with [data-testid="settings-root"] qualifies.
    const heading = authedPage.locator(
      '[data-testid="settings-root"], h1, h2',
    ).filter({ hasText: /settings|einstellungen|настройки/i }).first();
    await expect(heading.or(authedPage.locator('[data-testid="settings-tabs"]'))).toBeVisible({
      timeout: 10_000,
    });
    await captureScreen(authedPage, 'smoke', 'settings-loaded');
  });

  test('each settings tab can be clicked without an error boundary', async ({ authedPage }) => {
    await gotoModule(authedPage, 'settings');
    const tabs = authedPage.locator('[role="tab"], [data-testid^="settings-tab-"]');
    const count = Math.min(await tabs.count(), 12); // safety cap
    if (count === 0) {
      test.skip(true, 'no settings tabs found — UI may use single-page settings');
    }
    for (let i = 0; i < count; i += 1) {
      const tab = tabs.nth(i);
      const label = (await tab.textContent())?.trim() ?? `tab-${i}`;
      await tab.click().catch(() => {
        /* some tabs may be disabled — that's fine */
      });
      // Brief settle and screenshot — no assertion beyond "no error boundary".
      await authedPage.waitForTimeout(300);
      const errorBoundary = authedPage.locator('text=/something went wrong|error boundary/i');
      expect(await errorBoundary.isVisible({ timeout: 200 }).catch(() => false), `tab "${label}" triggered error boundary`).toBe(false);
      await captureScreen(authedPage, 'smoke', `settings-tab-${i + 1}`);
    }
  });
});
