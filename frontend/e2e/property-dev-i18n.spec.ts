/**
 * Property Development i18n coverage smoke-test.
 *
 * For 6 representative locales (en, de, ru, fr, ar, ja):
 *   1. Navigate to /property-dev with ?lang=<locale>
 *   2. Screenshot the page
 *   3. Open the (first) buyer drawer (or "create buyer" modal as fallback)
 *   4. Screenshot the drawer
 *   5. For RTL locales (ar, he) — assert dir="rtl" on <html>
 *   6. Assert no visible `[propdev.xxx]` placeholder / raw-key fallback
 *
 * Artifacts: .tests-artifacts/r6/property_dev_i18n/<locale>_page.png
 *            .tests-artifacts/r6/property_dev_i18n/<locale>_drawer.png
 *
 * Run:
 *   npx playwright test e2e/property-dev-i18n.spec.ts
 */
import { test, expect, type Page } from '@playwright/test';
import { login } from './helpers';

const ARTIFACTS_DIR = '.tests-artifacts/r6/property_dev_i18n';

const LOCALES = ['en', 'de', 'ru', 'fr', 'ar', 'ja'] as const;
const RTL_LOCALES = new Set(['ar', 'he']);

async function gotoPropertyDev(page: Page, locale: string): Promise<void> {
  await page.goto(`/property-dev?lang=${locale}`);
  // Wait for the lazy locale chunk to load and the page to settle.
  await page.waitForLoadState('networkidle');
  // The page title is wrapped in <h1>, t('propdev.title', …).
  await expect(page.locator('h1').first()).toBeVisible({ timeout: 10_000 });
}

async function assertNoRawKeys(page: Page): Promise<void> {
  // No literal "propdev.xxx" strings should leak to the rendered DOM.
  // (i18next prints raw keys when neither resource nor fallback resolves.)
  const html = await page.content();
  const leaks = html.match(/\bpropdev\.[a-z_]+/g) ?? [];
  // Allow the key to appear inside script/JSON blobs — only fail on plain text.
  const visibleLeaks = leaks.filter(
    (k) =>
      // strip false positives from attribute names like data-key="propdev.x"
      !html.includes(`data-key="${k}"`) && !html.includes(`"${k}":`),
  );
  expect(visibleLeaks, `Raw propdev.* keys leaked into UI: ${visibleLeaks.join(', ')}`).toHaveLength(0);
}

test.describe('property-dev i18n coverage', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  for (const locale of LOCALES) {
    test(`renders fully translated /property-dev in ${locale}`, async ({ page }) => {
      await gotoPropertyDev(page, locale);

      // Verify RTL attribute applied for Arabic.
      if (RTL_LOCALES.has(locale)) {
        const dir = await page.locator('html').getAttribute('dir');
        expect(dir, `expected dir="rtl" for ${locale}`).toBe('rtl');
      }

      // Page-level screenshot.
      await page.screenshot({
        path: `${ARTIFACTS_DIR}/${locale}_page.png`,
        fullPage: true,
      });

      // Open the New Buyer drawer/modal — exposes form labels (full_name,
      // email, phone), which are the densest propdev.* surface.
      // Switch to the Buyers tab first if not already active.
      const buyersTab = page.getByRole('button', { name: /buyer|käufer|покупател|acquéreur|مشتر|購入/i }).first();
      if (await buyersTab.count()) {
        await buyersTab.click().catch(() => {});
      }

      // Click "New Buyer" primary button (top-right). Best-effort.
      const newBuyer = page
        .locator('button')
        .filter({ hasText: /\+|new buyer|neuer käufer|новый покупатель|nouvel acquéreur|مشترٍ جديد|新規購入者/i })
        .first();
      if (await newBuyer.count()) {
        await newBuyer.click().catch(() => {});
        await page.waitForTimeout(500); // modal open animation
      }

      await page.screenshot({
        path: `${ARTIFACTS_DIR}/${locale}_drawer.png`,
        fullPage: true,
      });

      await assertNoRawKeys(page);
    });
  }
});
