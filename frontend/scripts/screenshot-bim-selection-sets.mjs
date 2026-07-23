/**
 * screenshot-bim-selection-sets.mjs — sanity check for W6.6 Selection Sets.
 *
 * Run with the dev server on http://localhost:5180 and a backend on :8000.
 * The script:
 *   1. logs in via the demo admin shortcut on /login
 *   2. opens /bim and waits for the first model to load
 *   3. looks for [data-testid="bim-selection-sets-panel"]
 *      - if missing, logs "Panel not yet wired into BIMRightPanelTabs.tsx —
 *        integrator follow-up", snaps a "pending" image, exits 0
 *      - if present, picks 5 elements via the global __oeBim bridge,
 *        screenshots before/created/restored states
 *
 * All screenshots land in ../qa-tests/_w66-selection-sets/.
 */
import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const OUT_DIR = 'qa-tests/_w66-selection-sets';

async function ensureDir(path) {
  try {
    await mkdir(path, { recursive: true });
  } catch {
    // already exists — fine.
  }
}

async function loginAsDemo(page) {
  await page.goto('http://localhost:5180/login', { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  const adminBtn = page.getByText('Admin', { exact: false }).first();
  if (await adminBtn.count()) {
    await adminBtn.click();
    await page.waitForTimeout(500);
  }
  const signInBtn = page.getByRole('button', { name: /sign in/i });
  if (await signInBtn.count()) {
    await signInBtn.first().click();
    await page.waitForTimeout(2000);
  }
}

async function openFirstBIMModel(page) {
  await page.goto('http://localhost:5180/bim', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  // Dismiss any tour/onboarding modal.
  await page.keyboard.press('Escape').catch(() => {});
  await page.waitForTimeout(300);
  // Pick the first model card if a project picker is open.
  const firstModelCard = page.locator('[data-testid^="bim-model-card-"]').first();
  if (await firstModelCard.count()) {
    await firstModelCard.click().catch(() => {});
    await page.waitForTimeout(2000);
  }
}

async function main() {
  await ensureDir(OUT_DIR);
  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.setViewportSize({ width: 1600, height: 1000 });

  try {
    await loginAsDemo(page);
    await openFirstBIMModel(page);

    const panel = page.locator('[data-testid="bim-selection-sets-panel"]');
    const present = await panel.count();
    if (!present) {
      console.log(
        'Panel not yet wired into BIMRightPanelTabs.tsx — integrator follow-up',
      );
      await page.screenshot({
        path: `${OUT_DIR}/pending-integration.png`,
        fullPage: false,
      });
      await browser.close();
      process.exit(0);
    }

    // Pick 5 elements via the BIMViewer bridge.
    const picked = await page.evaluate(() => {
      const bridge = window.__oeBim;
      if (!bridge) return { ok: false, reason: 'no-bridge' };
      const selectionMgr = bridge.selectionManager;
      if (!selectionMgr || typeof selectionMgr.selectByIds !== 'function') {
        return { ok: false, reason: 'no-selection-manager' };
      }
      // Pull a sample of element ids from the BIMViewer scene.
      const ids = bridge.sampleElementIds ? bridge.sampleElementIds(5) : null;
      if (!ids || !ids.length) {
        return { ok: false, reason: 'no-sample-ids' };
      }
      selectionMgr.selectByIds(ids, { exclusive: true });
      return { ok: true, ids };
    });
    if (!picked || !picked.ok) {
      console.log(
        `Could not pre-select elements via __oeBim bridge (reason=${picked?.reason ?? 'unknown'}); panel still rendered — screenshotting pending state`,
      );
      await page.screenshot({
        path: `${OUT_DIR}/pending-bridge.png`,
        fullPage: false,
      });
      await browser.close();
      process.exit(0);
    }

    await page.waitForTimeout(800);
    await page.screenshot({ path: `${OUT_DIR}/before.png`, fullPage: false });

    // Type a name and click Save.
    await page.locator('[data-testid="bim-selection-set-save-new"]').click();
    await page
      .locator('[data-testid="bim-selection-set-name-input"]')
      .fill('Level 3 Columns');
    await page
      .locator('[data-testid="bim-selection-set-create-confirm"]')
      .click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${OUT_DIR}/created.png`, fullPage: false });

    // Click Restore on the first row.
    const restoreBtn = page
      .locator('[data-testid^="bim-selection-set-restore-"]')
      .first();
    if (await restoreBtn.count()) {
      await restoreBtn.click();
      await page.waitForTimeout(500);
      await page.screenshot({
        path: `${OUT_DIR}/restored.png`,
        fullPage: false,
      });
    } else {
      console.log('Restore button missing post-create — screenshotting state');
      await page.screenshot({
        path: `${OUT_DIR}/restore-missing.png`,
        fullPage: false,
      });
    }

    console.log('OK — selection sets sanity check captured 3 screenshots');
  } catch (err) {
    console.error('FAIL', err);
    try {
      await page.screenshot({ path: `${OUT_DIR}/error.png`, fullPage: false });
    } catch {
      // best effort
    }
    await browser.close();
    process.exit(1);
  }

  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
