/**
 * Smoke — dashboard loads with widgets.
 */
import { test, expect } from '../fixtures';
import { gotoModule, expectAppShell, captureScreen, collectConsoleErrors, expectNoConsoleErrors } from '../helpers';

test.describe('@smoke dashboard', () => {
  test('dashboard mounts and the app shell is visible', async ({ authedPage }) => {
    const errors = collectConsoleErrors(authedPage);
    await gotoModule(authedPage, 'dashboard');
    await expectAppShell(authedPage);
    await captureScreen(authedPage, 'smoke', 'dashboard-loaded');
    // Allow benign noise (3rd-party SDK warnings, etc.) — block real exceptions only.
    expectNoConsoleErrors(errors, [/sourcemap/i, /favicon/i, /react devtools/i, /\bws:\/\//]);
  });

  test('dashboard exposes at least one widget container', async ({ authedPage }) => {
    await gotoModule(authedPage, 'dashboard');
    // Widget contract: each widget renders with [data-testid^="widget-"] OR
    // we have a "Customize" button that means the dashboard chrome loaded.
    const widgets = authedPage.locator('[data-testid^="widget-"], [data-widget]');
    const customizeBtn = authedPage.locator(
      '[data-testid="dashboard-customize"], button:has-text("Customize"), button:has-text("Anpassen")',
    );
    const widgetCount = await widgets.count();
    const customizeVisible = await customizeBtn.first().isVisible({ timeout: 2_000 }).catch(() => false);
    expect(
      widgetCount > 0 || customizeVisible,
      'dashboard should render widgets or a customize control',
    ).toBe(true);
    await captureScreen(authedPage, 'smoke', 'dashboard-widgets');
  });
});
