// Full /match-elements workflow exerciser. Logs API failures so we can fix them.

import { chromium } from 'playwright';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const __dirname_esm = path.dirname(fileURLToPath(import.meta.url));
const OUT_NAME = process.env.OUT_NAME || '_match-elements-workflow';
const OUT = path.resolve(__dirname_esm, '../../qa-tests/' + OUT_NAME);
fs.mkdirSync(OUT, { recursive: true });

const FRONTEND = 'http://localhost:5180';
const BACKEND = 'http://localhost:8000';
const USER = { email: 'v19-e2e@openestimate.com', password: 'OpenEstimate2024!' };

async function login() {
  let res = await fetch(`${BACKEND}/api/v1/users/auth/login/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: USER.email, password: USER.password }),
  });
  if (!res.ok) {
    await fetch(`${BACKEND}/api/v1/users/auth/register/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(USER),
    });
    res = await fetch(`${BACKEND}/api/v1/users/auth/login/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: USER.email, password: USER.password }),
    });
  }
  if (!res.ok) throw new Error(`login failed ${res.status}`);
  return res.json();
}

const issues = [];
const consoleErrors = [];
const networkFailures = [];

(async () => {
  const t = await login();
  const access = t.access_token;
  const refresh = t.refresh_token ?? access;
  console.log('✓ login');

  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  page.on('console', (m) => {
    if (m.type() === 'error') {
      consoleErrors.push(m.text());
    }
  });
  page.on('response', (r) => {
    if (r.url().includes('/api/v1/match_elements') && r.status() >= 400) {
      networkFailures.push(`${r.status()} ${r.request().method()} ${r.url()}`);
    }
  });

  await page.goto(`${FRONTEND}/about`);
  await page.evaluate(
    ({ access, refresh, email }) => {
      localStorage.setItem('oe_access_token', access);
      localStorage.setItem('oe_refresh_token', refresh);
      localStorage.setItem('oe_user_email', email);
      localStorage.setItem('oe_update_dismissed_version', '99.99.99');
      localStorage.setItem('oe_onboarding_completed', 'true');
      localStorage.setItem('oe_first_run', '0');
    },
    { access, refresh, email: USER.email },
  );

  async function dismissModals() {
    // ONLY clear update-checker / onboarding modals — leave /match-elements
    // panels alone (their close buttons would otherwise be triggered).
    for (const sel of [
      'button:has-text("Got it")',
      'button:has-text("Skip tour")',
    ]) {
      const el = page.locator(sel).first();
      if (await el.isVisible().catch(() => false)) {
        await el.click({ timeout: 1000 }).catch(() => null);
        await page.waitForTimeout(200);
      }
    }
  }
  async function shot(name) {
    await dismissModals();
    await page.screenshot({ path: path.join(OUT, name), fullPage: true });
    console.log('  shot', name);
  }
  async function shotViewport(name) {
    await dismissModals();
    await page.screenshot({ path: path.join(OUT, name) });
    console.log('  shot', name);
  }

  // STEP 1: Land on /match-elements
  console.log('\nSTEP 1: navigate to /match-elements');
  await page.goto(`${FRONTEND}/match-elements`);
  await page.waitForLoadState('networkidle').catch(() => null);
  await page.waitForTimeout(2500);
  await dismissModals();
  await shot('01-landing.png');

  // Capture project name + group count
  const projectSelect = page.locator('select').first();
  const projectName = await projectSelect.evaluate((el) => el.options[el.selectedIndex]?.text).catch(() => 'unknown');
  console.log('  project:', projectName);

  // STEP 2: Run vector match
  console.log('\nSTEP 2: Run vector match (all groups)');
  const vec = page.locator('button:has-text("vector match")').first();
  await vec.click();
  await page.waitForTimeout(500);
  await shot('02-vector-running.png');
  // Wait for the busy banner to clear (vector matcher over 599K vectors can take a while)
  for (let i = 0; i < 180; i++) {
    const busy = await page.locator('text=Running').first().isVisible().catch(() => false);
    if (!busy) break;
    await page.waitForTimeout(1000);
  }
  await page.waitForTimeout(800);
  await shot('03-vector-done.png');

  // STEP 3: Click Detail on first group
  console.log('\nSTEP 3: Open detail panel');
  const firstDetail = page.locator('table button:has-text("Detail")').first();
  if (await firstDetail.isVisible().catch(() => false)) {
    await firstDetail.click();
    // Wait until the slide-over <aside> actually renders.
    await page.locator('aside.fixed.right-0').first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => null);
    await page.waitForTimeout(2500);
    const asideVisible = await page.locator('aside.fixed.right-0').first().isVisible().catch(() => false);
    console.log('  detail panel visible:', asideVisible);
    await shotViewport('04-detail-methods.png');

    // Switch tabs via dispatchEvent — backdrop interception trips Playwright's
    // actionability even though z-50 aside paints on top of z-40 backdrop.
    const elTab = page.locator('aside.fixed.right-0 button:has-text("Elements")').first();
    if (await elTab.isVisible().catch(() => false)) {
      await elTab.dispatchEvent('click');
      await page.waitForTimeout(700);
      await shotViewport('05-detail-elements.png');
    }
    const apTab = page.locator('aside.fixed.right-0 button:has-text("Apply preview")').first();
    if (await apTab.isVisible().catch(() => false)) {
      await apTab.dispatchEvent('click');
      await page.waitForTimeout(1500);
      await shotViewport('06-detail-apply.png');
    }

    // STEP 4: Try Confirm on first candidate
    console.log('\nSTEP 4: Confirm first candidate');
    const methodsTab = page.locator('aside.fixed.right-0 button:has-text("Match candidates")').first();
    if (await methodsTab.isVisible().catch(() => false)) await methodsTab.dispatchEvent('click');
    await page.waitForTimeout(700);
    const confirmBtn = page.locator('aside.fixed.right-0 button:has-text("Confirm")').first();
    if (await confirmBtn.isVisible().catch(() => false)) {
      await confirmBtn.dispatchEvent('click');
      await page.waitForTimeout(1500);
      await shotViewport('07-after-confirm.png');
    } else {
      console.log('  no candidates available — skipping confirm');
    }

    // STEP 5: No-match flow
    console.log('\nSTEP 5: No-match modal');
    const noMatchBtn = page.locator('aside.fixed.right-0 button:has-text("No match")').first();
    if (await noMatchBtn.isVisible().catch(() => false)) {
      await noMatchBtn.dispatchEvent('click');
      await page.waitForTimeout(700);
      await shotViewport('08-no-match-modal.png');
      // Cancel
      const cancel = page.locator('button:has-text("Cancel")').first();
      if (await cancel.isVisible().catch(() => false)) await cancel.click();
      await page.waitForTimeout(400);
    }

    // Close detail panel
    const closeBtn = page.locator('aside header button').first();
    if (await closeBtn.isVisible().catch(() => false)) {
      await closeBtn.click().catch(() => null);
      await page.waitForTimeout(300);
    }
  }

  // STEP 6: Multi-select + bulk confirm
  console.log('\nSTEP 6: Multi-select + bulk confirm');
  const checks = page.locator('table input[type="checkbox"]').nth(1); // skip header
  if (await checks.isVisible().catch(() => false)) {
    await checks.click();
    const checks2 = page.locator('table input[type="checkbox"]').nth(2);
    if (await checks2.isVisible().catch(() => false)) await checks2.click();
    await page.waitForTimeout(400);
    await shot('09-multiselect.png');

    const conf = page.locator('button:has-text("Confirm")').first();
    if (await conf.isVisible().catch(() => false)) {
      await conf.click();
      // Auto-accepts the alert
      page.on('dialog', (d) => d.accept().catch(() => null));
      await page.waitForTimeout(2500);
      await shot('10-after-bulk-confirm.png');
    }
  }

  // STEP 7: Templates panel
  console.log('\nSTEP 7: Templates panel');
  const lib = page.locator('button:has-text("Library")').first();
  if (await lib.isVisible().catch(() => false)) {
    await lib.click();
    await page.waitForTimeout(800);
    await shotViewport('11-templates-panel.png');
  }

  // STEP 8: Run lexical + resources matchers
  console.log('\nSTEP 8: Run lexical + resources matchers');
  // Close any open slide-over via the panel's X button (most reliable — bypasses backdrop click stacking).
  for (let i = 0; i < 5; i++) {
    const xBtn = page.locator('aside.fixed.right-0 header button:has(svg.lucide-x)').first();
    if (!(await xBtn.isVisible().catch(() => false))) break;
    await xBtn.click({ force: true }).catch(() => null);
    await page.waitForTimeout(400);
  }
  // Belt-and-braces: also tap Escape + click outside.
  await page.keyboard.press('Escape').catch(() => null);
  await page.waitForTimeout(200);

  const lex = page.locator('button:has-text("lexical")').first();
  if (await lex.isVisible().catch(() => false)) {
    await lex.click();
    await page.waitForTimeout(8000);
    await shot('12-after-lexical.png');
  }
  const rsrc = page.locator('button:has-text("Match resources")').first();
  if (await rsrc.isVisible().catch(() => false)) {
    await rsrc.click();
    await page.waitForTimeout(8000);
    await shot('13-after-resources.png');
  }

  await browser.close();

  console.log('\n=== SUMMARY ===');
  console.log('Console errors:', consoleErrors.length);
  consoleErrors.slice(0, 10).forEach((e) => console.log('  ', e));
  console.log('match_elements 4xx/5xx:', networkFailures.length);
  networkFailures.slice(0, 20).forEach((f) => console.log('  ', f));
  console.log('Issues recorded:', issues.length);
  issues.forEach((i) => console.log('  ', i));
  console.log('\nScreenshots in', OUT);
})().catch((e) => {
  console.error('SPEC ERROR:', e);
  process.exit(1);
});
