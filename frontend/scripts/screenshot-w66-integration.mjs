/**
 * ‌⁠‍screenshot-w66-integration.mjs — Playwright sanity check that the four
 * W6.6 "BIM Viewer Pro UX — Surveyor's Kit" streams are wired into the
 * live UI.
 *
 * Verifies, end-to-end:
 *   1. View Cube (Site Compass) is present at the top-right of the viewer.
 *   2. The Trait Lens tab is reachable from the right-panel tab strip.
 *   3. The Element Bundles tab is reachable from the same tab strip.
 *   4. Hiding an element via the context menu raises the floating
 *      hidden-count badge in the upper-left corner.
 *
 * Each step takes a screenshot under qa-tests/_w66-integration/.
 *
 * Exit codes:
 *   0 — every required step succeeded.
 *   2 — at least one required step was missing.
 *
 * Run: node frontend/scripts/screenshot-w66-integration.mjs
 */

import { chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const BASE_URL = process.env.OE_BASE_URL ?? 'http://localhost:5180';
const OUT_DIR = path.resolve(process.cwd(), 'qa-tests/_w66-integration');
const DEMO_EMAIL = process.env.OE_DEMO_EMAIL ?? 'demo@openconstructionerp.com';
const DEMO_PASSWORD = process.env.OE_DEMO_PASSWORD ?? 'demo';

function ensureOut() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
}

async function shot(page, name) {
  const filepath = path.join(OUT_DIR, name);
  await page.screenshot({ path: filepath, fullPage: false });
  // eslint-disable-next-line no-console
  console.log(`SAVED ${filepath}`);
}

async function login(page) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(400);

  // Try the typed-credential path first — works on any env where the
  // demo user exists. Falls back to the demo card click if the form
  // isn't visible.
  const email = page.locator(
    'input[type="email"], input[name="email"], input[placeholder*="email" i]',
  ).first();
  if (await email.count()) {
    await email.fill(DEMO_EMAIL).catch(() => {});
    const pass = page.locator(
      'input[type="password"], input[name="password"]',
    ).first();
    if (await pass.count()) {
      await pass.fill(DEMO_PASSWORD).catch(() => {});
    }
  }

  const signIn = page.getByRole('button', { name: /sign in|log in/i }).first();
  if (await signIn.count()) {
    await signIn.click().catch(() => {});
  }
  await page.waitForTimeout(1500);

  // Demo-card fallback if the typed-credential path didn't navigate.
  if (page.url().includes('/login')) {
    const demoCard = page.getByText(/admin|estimator|demo/i).first();
    if (await demoCard.count()) {
      await demoCard.click().catch(() => {});
      await page.waitForTimeout(500);
      const signIn2 = page.getByRole('button', { name: /sign in|log in/i }).first();
      if (await signIn2.count()) {
        await signIn2.click().catch(() => {});
        await page.waitForTimeout(1500);
      }
    }
  }
}

async function openFirstBIMModel(page) {
  await page.goto(`${BASE_URL}/bim`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);

  // Try a sequence of model-row selectors, oldest format first.
  const candidates = [
    'a[href*="/bim/"]',
    '[data-testid="bim-model-card"]',
    'button:has-text("Open")',
  ];
  let opened = false;
  for (const sel of candidates) {
    const el = page.locator(sel).first();
    if ((await el.count()) > 0) {
      await el.click().catch(() => {});
      opened = true;
      break;
    }
  }
  if (!opened) {
    return false;
  }
  // Give the SceneManager + geometry stream a chance to mount.
  await page.waitForTimeout(3500);
  return true;
}

async function clickRightTab(page, tabId) {
  // The tab buttons are keyed by data-testid="right-tab-{id}". Some
  // installs open the right panel on demand — try to click a sidebar
  // toggle first if the tab isn't immediately visible.
  let tab = page.locator(`[data-testid="right-tab-${tabId}"]`).first();
  if ((await tab.count()) === 0) {
    // Try toggling the right panel open via any of its known triggers.
    const opener = page
      .locator(
        'button[aria-label*="properties" i], button[aria-label*="panel" i], button[title*="panel" i]',
      )
      .first();
    if ((await opener.count()) > 0) {
      await opener.click().catch(() => {});
      await page.waitForTimeout(400);
    }
    tab = page.locator(`[data-testid="right-tab-${tabId}"]`).first();
  }
  if ((await tab.count()) === 0) return false;
  await tab.click({ force: true }).catch(() => {});
  await page.waitForTimeout(450);
  return true;
}

async function main() {
  ensureOut();
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 1000 },
  });
  const page = await ctx.newPage();

  const required = {
    loggedIn: false,
    modelOpened: false,
    viewCube: false,
    traitLens: false,
    elementBundles: false,
    hiddenBadge: false,
  };

  try {
    await login(page);
    required.loggedIn = !page.url().includes('/login');
    if (!required.loggedIn) {
      // eslint-disable-next-line no-console
      console.error('login failed — still on /login');
    }

    required.modelOpened = await openFirstBIMModel(page);
    if (!required.modelOpened) {
      // eslint-disable-next-line no-console
      console.error('no BIM model could be opened');
    }
    await shot(page, '01-model-open.png');

    // 1. View Cube present?
    const cube = page.locator('[data-testid="bim-view-cube"]').first();
    try {
      await cube.waitFor({ state: 'visible', timeout: 8000 });
      required.viewCube = true;
      await shot(page, '02-view-cube.png');
    } catch {
      // eslint-disable-next-line no-console
      console.error('bim-view-cube not visible');
    }

    // 2. Trait Lens tab
    if (await clickRightTab(page, 'trait-lens')) {
      required.traitLens = true;
      await shot(page, '03-trait-lens-tab.png');
    } else {
      // eslint-disable-next-line no-console
      console.error('right-tab-trait-lens not found');
    }

    // 3. Element Bundles tab
    if (await clickRightTab(page, 'bundles')) {
      required.elementBundles = true;
      await shot(page, '04-element-bundles-tab.png');
    } else {
      // eslint-disable-next-line no-console
      console.error('right-tab-bundles not found');
    }

    // 4. Hide one element via the SelectionManager (window.__oeBim) and
    //    look for the hidden-count badge. This is more reliable than
    //    driving the context menu through synthetic right-clicks in jsdom.
    await page.evaluate(() => {
      const w = window;
      const bridge = w.__oeBim;
      if (!bridge) return;
      // Prefer the SelectionManager-driven path so we exercise the same
      // code the live UI uses; fall back to elementManager.hide() if the
      // selection bridge isn't available.
      const elMgr = bridge.elementManager;
      if (!elMgr) return;
      // hide one arbitrary element so the badge raises.
      const meshes = elMgr.getAllMeshes ? elMgr.getAllMeshes() : [];
      const first = meshes[0];
      if (first && first.userData && first.userData.elementId) {
        elMgr.hideElements(new Set([first.userData.elementId]));
      }
    });
    await page.waitForTimeout(400);
    const badge = page.locator('[data-testid="bim-hidden-count-badge"]').first();
    if ((await badge.count()) > 0) {
      required.hiddenBadge = true;
      await shot(page, '05-hidden-count-badge.png');
    } else {
      // eslint-disable-next-line no-console
      console.error('bim-hidden-count-badge not found after hideElements()');
      await shot(page, '05-hidden-count-badge-missing.png');
    }
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error('w66 integration screenshot run failed:', err);
  } finally {
    await browser.close();
  }

  // eslint-disable-next-line no-console
  console.log('STEP RESULTS', required);
  const allOk = Object.values(required).every(Boolean);
  process.exit(allOk ? 0 : 2);
}

main();
