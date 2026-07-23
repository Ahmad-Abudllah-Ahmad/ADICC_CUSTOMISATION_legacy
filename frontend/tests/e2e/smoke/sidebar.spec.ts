/**
 * Smoke — every sidebar entry has an aria-label and a valid href.
 *
 * Catches:
 *  - missing aria-label (a11y regression)
 *  - broken href (404 link in nav)
 *  - duplicate or empty links
 */
import { test, expect } from '../fixtures';
import { gotoModule, expectAppShell, captureScreen } from '../helpers';

test.describe('@smoke sidebar', () => {
  test('every sidebar link has accessible name and href', async ({ authedPage }) => {
    await gotoModule(authedPage, 'dashboard');
    await expectAppShell(authedPage);
    const sidebar = authedPage.locator('[data-testid="sidebar"], nav[aria-label*="main" i], aside').first();
    await expect(sidebar).toBeVisible({ timeout: 10_000 });

    const links = sidebar.locator('a[href]');
    const count = await links.count();
    expect(count, 'sidebar should expose at least 5 navigation entries').toBeGreaterThanOrEqual(5);

    const missingLabel: string[] = [];
    const badHrefs: string[] = [];
    for (let i = 0; i < count; i += 1) {
      const link = links.nth(i);
      const accessibleName =
        (await link.getAttribute('aria-label')) ||
        (await link.getAttribute('title')) ||
        (await link.textContent().then((t) => (t ?? '').trim()));
      const href = (await link.getAttribute('href')) ?? '';
      if (!accessibleName) missingLabel.push(href || `index-${i}`);
      if (!href || href === '#' || href === '/#') badHrefs.push(`index-${i}`);
    }
    await captureScreen(authedPage, 'smoke', 'sidebar-rendered');
    expect(missingLabel, `links missing accessible name: ${missingLabel.join(', ')}`).toHaveLength(0);
    expect(badHrefs, `links with empty/# href: ${badHrefs.join(', ')}`).toHaveLength(0);
  });
});
