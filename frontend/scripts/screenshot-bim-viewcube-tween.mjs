// W6.6 Playwright sanity check for the BIM ViewCube + camera tween.
//
// Flow:
//   1. Log in (admin demo).
//   2. Navigate into /bim, open the first model card available.
//   3. Wait for the ViewCube to appear in the DOM.
//   4. Capture: baseline → TOP click → FRONT click → saved-view restore
//      mid-flight + final. Outputs go to qa-tests/_w66-viewcube-tween/.
//
// Run: node frontend/scripts/screenshot-bim-viewcube-tween.mjs

import { chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const BASE_URL = process.env.OE_BASE_URL ?? 'http://localhost:5180';
const OUT_DIR = path.resolve(process.cwd(), 'qa-tests/_w66-viewcube-tween');

async function ensureOut() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
}

async function login(page) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  // Click the "Admin" demo card if present.
  const demoBtn = page.getByText('Admin', { exact: false }).first();
  if (await demoBtn.count()) {
    await demoBtn.click().catch(() => {});
    await page.waitForTimeout(400);
  }
  const signInBtn = page.getByRole('button', { name: /sign in/i });
  if (await signInBtn.count()) {
    await signInBtn.first().click();
    await page.waitForTimeout(1500);
  }
}

async function openFirstBIMModel(page) {
  await page.goto(`${BASE_URL}/bim`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  // Click the first model card / row.
  const candidates = [
    'a[href*="/bim/"]',
    '[data-testid="bim-model-card"]',
    'button:has-text("Open")',
  ];
  for (const sel of candidates) {
    const el = page.locator(sel).first();
    if ((await el.count()) > 0) {
      await el.click().catch(() => {});
      break;
    }
  }
  await page.waitForTimeout(2500);
}

async function shot(page, name) {
  const filepath = path.join(OUT_DIR, name);
  await page.screenshot({ path: filepath, fullPage: false });
  console.log(`SAVED ${filepath}`);
}

async function main() {
  await ensureOut();
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
  const page = await ctx.newPage();

  try {
    await login(page);
    await openFirstBIMModel(page);

    // Wait until the ViewCube widget mounts. Skip the rest if it never
    // shows up (parent integrator hasn't wired it in yet — expected
    // during W6.6 transit period).
    const cube = page.locator('[data-testid="bim-view-cube"]');
    try {
      await cube.first().waitFor({ state: 'visible', timeout: 8000 });
    } catch {
      console.warn('view-cube not found — integrator has not wired it yet, capturing baseline only.');
      await shot(page, 'baseline.png');
      await browser.close();
      return;
    }

    await shot(page, 'baseline.png');

    // TOP face click → wait 700 ms → screenshot
    await page.locator('[data-testid="bim-view-cube-face-top"]').first().click({ force: true }).catch(() => {});
    await page.waitForTimeout(700);
    await shot(page, 'top.png');

    // FRONT face click → wait 700 ms → screenshot
    await page.locator('[data-testid="bim-view-cube-face-front"]').first().click({ force: true }).catch(() => {});
    await page.waitForTimeout(700);
    await shot(page, 'front.png');

    // Saved-view restore mid-flight / final.
    const savedViewBtn = page.locator('[data-testid^="saved-view-restore-"], button:has-text("Restore")').first();
    if ((await savedViewBtn.count()) > 0) {
      await savedViewBtn.click().catch(() => {});
      await page.waitForTimeout(350);
      await shot(page, 'tween-midflight.png');
      await page.waitForTimeout(400);
      await shot(page, 'tween-final.png');
    } else {
      console.warn('no saved-view restore button found — skipping tween mid-flight capture.');
    }
  } catch (err) {
    console.error('viewcube screenshot run failed:', err);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main();
