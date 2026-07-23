/**
 * Smoke — mobile responsive: sidebar collapses, no horizontal scroll.
 *
 * Tagged @mobile so it runs under the mobile-chromium project.
 */
import { test, expect } from '../fixtures';
import { gotoModule, captureScreen } from '../helpers';

test.describe('@smoke @mobile mobile-responsive', () => {
  test('dashboard fits in iPhone SE viewport without horizontal scroll', async ({ authedPage }) => {
    await gotoModule(authedPage, 'dashboard');
    const docWidth = await authedPage.evaluate(() => document.documentElement.scrollWidth);
    const winWidth = await authedPage.evaluate(() => window.innerWidth);
    // Allow 2px tolerance for sub-pixel rounding.
    expect(docWidth, `page is ${docWidth - winWidth}px wider than viewport`).toBeLessThanOrEqual(winWidth + 2);
    await captureScreen(authedPage, 'smoke', 'mobile-dashboard');
  });

  test('sidebar is collapsed by default on mobile', async ({ authedPage }) => {
    await gotoModule(authedPage, 'dashboard');
    // The full sidebar should be off-screen / hidden; a burger button should be visible.
    const burger = authedPage.locator(
      '[data-testid="sidebar-toggle"], button[aria-label*="menu" i], button[aria-label*="navigation" i]',
    ).first();
    const isBurgerVisible = await burger.isVisible({ timeout: 3_000 }).catch(() => false);
    expect(isBurgerVisible, 'mobile viewport should expose a sidebar toggle').toBe(true);
    await captureScreen(authedPage, 'smoke', 'mobile-sidebar-collapsed');
  });
});
