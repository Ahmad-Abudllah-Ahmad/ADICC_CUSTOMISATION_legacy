/**
 * Smoke — force a backend 500 and confirm the page renders a recovery
 * UI, NOT a white screen of death.
 *
 * Approach: intercept a known API call, return 500. The UI must render
 * its error boundary (or inline error toast) instead of unmounting.
 */
import { test, expect } from '../fixtures';
import { captureScreen } from '../helpers';

test.describe('@smoke error-boundary', () => {
  test('a 500 from /api/v1/projects/ renders an error UI, not a white screen', async ({ authedPage }) => {
    // Inject the 500 BEFORE navigation so the projects list call fails.
    await authedPage.route('**/api/v1/projects/**', (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'forced test failure' }),
        });
      }
      return route.continue();
    });
    await authedPage.goto('/projects');
    await authedPage.waitForLoadState('domcontentloaded');
    // The body must contain *something* visible — not a blank screen.
    const bodyText = (await authedPage.locator('body').textContent()) ?? '';
    expect(bodyText.trim().length, 'page rendered as white screen').toBeGreaterThan(20);
    // Look for an error indicator — toast, inline error, retry button, etc.
    const errorish = authedPage.locator(
      [
        '[role="alert"]',
        '[data-testid="error-boundary"]',
        '[data-testid^="toast-error"]',
        'text=/error|fehler|ошибка/i',
        'button:has-text(/retry|wiederholen|повтор/i)',
      ].join(', '),
    ).first();
    await expect(errorish, 'expected an error indicator (alert/toast/retry button)').toBeVisible({
      timeout: 10_000,
    });
    await captureScreen(authedPage, 'smoke', 'error-boundary-500');
  });
});
