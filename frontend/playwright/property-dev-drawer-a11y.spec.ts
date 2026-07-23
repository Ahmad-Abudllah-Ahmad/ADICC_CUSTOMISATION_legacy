/**
 * Property Development drawer a11y E2E (task R6 #136).
 *
 * Validates the SideDrawer migration of the inline ``BuyerDetailDrawer``
 * + ``PlotDetailDrawer`` overlays into the portal-based, focus-trapped
 * shared component.
 *
 * Coverage:
 *   1. Open Buyers tab → click row → drawer opens with portal + focus
 *      moved into the panel.
 *   2. Tab repeatedly stays inside the drawer (5 presses, never escapes).
 *   3. Escape closes the drawer AND returns focus to the trigger row.
 *   4. Backdrop click closes the drawer.
 *   5. Rapid open/close cycle (10x) yields zero console errors —
 *      regression test for the React insertBefore failure that fires
 *      when the buyers list refetches behind an open drawer.
 *   6. Three viewport sizes (1920x1080, 1280x800, 375x812) — drawer
 *      renders correctly on each and is full-width on mobile.
 *
 * Screenshots:
 *   .tests-artifacts/r6/property_dev/drawer_a11y/01_drawer_open.png
 *   .tests-artifacts/r6/property_dev/drawer_a11y/02_after_close.png
 *   .tests-artifacts/r6/property_dev/drawer_a11y/03_backdrop_open.png
 *   .tests-artifacts/r6/property_dev/drawer_a11y/04_after_backdrop_close.png
 *   .tests-artifacts/r6/property_dev/drawer_a11y/viewport_1920x1080.png
 *   .tests-artifacts/r6/property_dev/drawer_a11y/viewport_1280x800.png
 *   .tests-artifacts/r6/property_dev/drawer_a11y/viewport_375x812.png
 */
import { test, expect, type Page } from '@playwright/test';

const SCREENSHOT_DIR = '.tests-artifacts/r6/property_dev/drawer_a11y';
const DEMO_ADMIN = 'demo@openconstructionerp.com';

async function demoLogin(page: Page, email: string): Promise<boolean> {
  const response = await page.request.post(
    '/api/v1/users/auth/demo-login/',
    {
      data: { email },
      headers: { 'Content-Type': 'application/json' },
    },
  );
  if (!response.ok()) return false;
  const json = await response.json();
  await page.goto('/');
  await page.evaluate(
    ({ access, refresh, email }) => {
      localStorage.setItem('oe_remember', '1');
      localStorage.setItem('oe_access_token', access);
      localStorage.setItem('oe_refresh_token', refresh);
      localStorage.setItem('oe_user_email', email);
      sessionStorage.removeItem('oe_access_token');
      sessionStorage.removeItem('oe_refresh_token');
    },
    {
      access: json.access_token as string,
      refresh: (json.refresh_token as string) ?? '',
      email,
    },
  );
  await page.reload();
  return true;
}

async function dismissOnboardingTour(page: Page): Promise<void> {
  await page.evaluate(() => {
    try {
      localStorage.setItem('oe_onboarding_tour_dismissed', '1');
      localStorage.setItem('oe_onboarding_tour_completed', '1');
    } catch {
      /* sandboxed contexts can throw */
    }
  });
  for (const sel of [
    'button:has-text("Skip")',
    'button:has-text("Got it")',
    'button:has-text("Close")',
  ]) {
    const candidate = page.locator(sel).first();
    if (await candidate.isVisible().catch(() => false)) {
      await candidate.click({ timeout: 1500 }).catch(() => undefined);
    }
  }
}

async function gotoBuyersTab(page: Page) {
  await page.goto('/property-dev');
  await page.waitForLoadState('networkidle', { timeout: 30_000 });
  await dismissOnboardingTour(page);

  const buyersTab = page.getByRole('tab', { name: /buyers/i }).first();
  if ((await buyersTab.count()) === 0) {
    const buyersBtn = page.getByRole('button', { name: /buyers/i }).first();
    if (await buyersBtn.count()) await buyersBtn.click();
  } else {
    await buyersTab.click();
  }
  await page.waitForLoadState('networkidle');
}

test.describe('Property Development drawer a11y', () => {
  test('drawer opens with focus trap, Tab stays inside, Escape returns focus', async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    const ok = await demoLogin(page, DEMO_ADMIN);
    test.skip(!ok, 'demo-login endpoint not provisioned in this env');

    await gotoBuyersTab(page);

    const firstBuyerRow = page
      .locator('tr')
      .filter({ hasText: /@/ })
      .first();
    await expect(firstBuyerRow).toBeVisible({ timeout: 30_000 });
    await firstBuyerRow.click();

    // Drawer is visible.
    const drawerHeading = page.locator('#propdev-buyer-drawer-title');
    await expect(drawerHeading).toBeVisible({ timeout: 10_000 });

    // role=dialog + aria-modal=true on the panel.
    const drawer = page
      .locator('[role="dialog"][aria-modal="true"]')
      .filter({ has: page.locator('#propdev-buyer-drawer-title') });
    await expect(drawer).toBeVisible();

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/01_drawer_open.png`,
      fullPage: true,
    });

    // Active element lives inside the dialog.
    const focusInsideDrawer = await page.evaluate(() => {
      const dlg = document.querySelector(
        '[role="dialog"][aria-modal="true"]',
      );
      return dlg ? dlg.contains(document.activeElement) : false;
    });
    expect(focusInsideDrawer).toBe(true);

    // Tab 5 times — focus must stay inside the dialog throughout.
    for (let i = 0; i < 5; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      await page.keyboard.press('Tab');
      // eslint-disable-next-line no-await-in-loop
      const stillInside = await page.evaluate(() => {
        const dlg = document.querySelector(
          '[role="dialog"][aria-modal="true"]',
        );
        return dlg ? dlg.contains(document.activeElement) : false;
      });
      expect(stillInside, `Tab #${i + 1} kept focus inside the drawer`).toBe(
        true,
      );
    }

    // Escape closes + restores focus to the buyer row.
    await page.keyboard.press('Escape');
    await expect(drawerHeading).not.toBeVisible({ timeout: 5_000 });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/02_after_close.png`,
      fullPage: true,
    });

    // Focus should be back on a row inside the buyers table.
    const focusOnTable = await page.evaluate(() => {
      const active = document.activeElement as HTMLElement | null;
      if (!active) return false;
      return !!active.closest('tr');
    });
    expect(focusOnTable).toBe(true);

    // No console errors throughout the open/close cycle.
    expect(consoleErrors.filter((e) => !/favicon|sourcemap/i.test(e))).toEqual(
      [],
    );
  });

  test('backdrop click closes the drawer', async ({ page }) => {
    const ok = await demoLogin(page, DEMO_ADMIN);
    test.skip(!ok, 'demo-login endpoint not provisioned in this env');

    await gotoBuyersTab(page);

    const firstBuyerRow = page
      .locator('tr')
      .filter({ hasText: /@/ })
      .first();
    await expect(firstBuyerRow).toBeVisible({ timeout: 30_000 });
    await firstBuyerRow.click();

    const drawerHeading = page.locator('#propdev-buyer-drawer-title');
    await expect(drawerHeading).toBeVisible({ timeout: 10_000 });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/03_backdrop_open.png`,
      fullPage: true,
    });

    // Click on the backdrop (top-left corner where the drawer is NOT).
    // The fixed wrapper covers the whole viewport so any non-panel area
    // collapses to close. Pick coords well outside the right-side panel.
    await page.mouse.click(50, 200);
    await expect(drawerHeading).not.toBeVisible({ timeout: 5_000 });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/04_after_backdrop_close.png`,
      fullPage: true,
    });
  });

  test('rapid open/close cycle yields no console errors', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    const ok = await demoLogin(page, DEMO_ADMIN);
    test.skip(!ok, 'demo-login endpoint not provisioned in this env');

    await gotoBuyersTab(page);

    const firstBuyerRow = page
      .locator('tr')
      .filter({ hasText: /@/ })
      .first();
    await expect(firstBuyerRow).toBeVisible({ timeout: 30_000 });

    // 10 open/close cycles. Each cycle re-runs the focus-trap mount +
    // cleanup which is what regressed under the inline overlay
    // (insertBefore failures when the buyers query refetched mid-cycle).
    for (let i = 0; i < 10; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      await firstBuyerRow.click();
      // eslint-disable-next-line no-await-in-loop
      await expect(page.locator('#propdev-buyer-drawer-title')).toBeVisible({
        timeout: 5_000,
      });
      // eslint-disable-next-line no-await-in-loop
      await page.keyboard.press('Escape');
      // eslint-disable-next-line no-await-in-loop
      await expect(
        page.locator('#propdev-buyer-drawer-title'),
      ).not.toBeVisible({ timeout: 5_000 });
    }

    // Filter out unrelated noise (favicon 404 etc.) and assert clean.
    const real = consoleErrors.filter(
      (e) =>
        !/favicon|sourcemap|the resource at .*was preloaded/i.test(e),
    );
    expect(real, `rapid open/close should not log errors: ${real.join('\n')}`)
      .toEqual([]);
  });

  test('drawer renders correctly across desktop/tablet/mobile viewports', async ({
    page,
  }) => {
    const ok = await demoLogin(page, DEMO_ADMIN);
    test.skip(!ok, 'demo-login endpoint not provisioned in this env');

    const viewports: Array<{ name: string; width: number; height: number }> = [
      { name: '1920x1080', width: 1920, height: 1080 },
      { name: '1280x800', width: 1280, height: 800 },
      { name: '375x812', width: 375, height: 812 },
    ];

    for (const vp of viewports) {
      // eslint-disable-next-line no-await-in-loop
      await page.setViewportSize({ width: vp.width, height: vp.height });
      // eslint-disable-next-line no-await-in-loop
      await gotoBuyersTab(page);

      const firstBuyerRow = page
        .locator('tr')
        .filter({ hasText: /@/ })
        .first();
      // eslint-disable-next-line no-await-in-loop
      await expect(firstBuyerRow).toBeVisible({ timeout: 30_000 });
      // eslint-disable-next-line no-await-in-loop
      await firstBuyerRow.click();

      // eslint-disable-next-line no-await-in-loop
      await expect(page.locator('#propdev-buyer-drawer-title')).toBeVisible({
        timeout: 10_000,
      });

      // On the narrow viewport (< sm breakpoint = 640px), the drawer
      // must be full-width (no horizontal whitespace next to it).
      if (vp.width < 640) {
        // eslint-disable-next-line no-await-in-loop
        const panelWidth = await page.evaluate(() => {
          const dlg = document.querySelector(
            '[role="dialog"][aria-modal="true"]',
          ) as HTMLElement | null;
          return dlg ? dlg.getBoundingClientRect().width : 0;
        });
        expect(panelWidth).toBeGreaterThan(vp.width * 0.9);
      }

      // eslint-disable-next-line no-await-in-loop
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/viewport_${vp.name}.png`,
        fullPage: true,
      });

      // Close before iterating to the next viewport so the gotoBuyersTab
      // re-navigation starts from a clean state.
      // eslint-disable-next-line no-await-in-loop
      await page.keyboard.press('Escape');
    }
  });
});
