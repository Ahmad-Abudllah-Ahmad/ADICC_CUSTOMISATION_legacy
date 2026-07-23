// Click probe for the role="button" cards we converted from <button> to
// <div role="button"> in v2.9.32. Verifies the cards still select on click
// (this is the regression I'm worried about — easy to break click semantics
// when refactoring keyboard handlers).

import { chromium } from 'playwright';

const FRONTEND = 'http://localhost:5180';
const BACKEND = 'http://localhost:8000';
const USER = { email: 'v19-e2e@openestimate.com', password: 'OpenEstimate2024!' };

async function login() {
  const r = await fetch(`${BACKEND}/api/v1/users/auth/login/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: USER.email, password: USER.password }),
  });
  return r.json();
}

(async () => {
  const t = await login();
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

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
    { access: t.access_token, refresh: t.refresh_token ?? t.access_token, email: USER.email },
  );

  // ── /bim ModelCard ─────────────────────────────────────────────────
  console.log('\n/bim — clicking second model card');
  await page.goto(`${FRONTEND}/bim`);
  await page.waitForLoadState('networkidle').catch(() => null);
  await page.waitForTimeout(1500);

  // Find all model cards. After my refactor they are <div role="button">.
  const cards = page.locator('[role="button"][tabindex="0"]').filter({ has: page.locator('text=elements') });
  const count = await cards.count();
  console.log(`  found ${count} ModelCards`);

  if (count >= 2) {
    // Click second card (avoid clicking the active one)
    const second = cards.nth(1);
    const before = await second.evaluate((el) =>
      el.className.includes('border-oe-blue') ? 'active' : 'inactive',
    );
    await second.click();
    await page.waitForTimeout(800);
    const after = await second.evaluate((el) =>
      el.className.includes('border-oe-blue') ? 'active' : 'inactive',
    );
    console.log(`  state before click: ${before}, after click: ${after}`);
    if (before !== 'active' && after === 'active') {
      console.log('  ✓ click selected the card (works)');
    } else if (before === 'active') {
      console.log('  ⚠ second card was already active — try first card');
      const first = cards.nth(0);
      await first.click();
      await page.waitForTimeout(800);
      const firstAfter = await first.evaluate((el) =>
        el.className.includes('border-oe-blue') ? 'active' : 'inactive',
      );
      console.log(`  first card after click: ${firstAfter}`);
    } else {
      console.log('  ✗ click did NOT select the card (REGRESSION)');
    }

    // Also test keyboard activation
    console.log('  testing Enter-key activation on a card');
    await cards.nth(0).focus();
    await page.keyboard.press('Enter');
    await page.waitForTimeout(800);
    const enterTarget = cards.nth(0);
    const afterEnter = await enterTarget.evaluate((el) =>
      el.className.includes('border-oe-blue') ? 'active' : 'inactive',
    );
    console.log(`  first card after Enter-key: ${afterEnter}`);
  } else {
    console.log('  (not enough cards in dev DB to test)');
  }

  // Trash icon on a card should NOT trigger card-select
  console.log('  hover-revealing trash icon and clicking it');
  if (count >= 1) {
    const card = cards.nth(0);
    await card.hover();
    await page.waitForTimeout(300);
    const trash = card.locator('button[aria-label*="Delete"]').first();
    if (await trash.isVisible().catch(() => false)) {
      // We don't actually want to delete — just confirm the click target
      // exists and is a real <button>. Don't click it (would delete).
      const tag = await trash.evaluate((el) => el.tagName);
      console.log(`  trash icon tag: ${tag} (expect BUTTON)`);
    } else {
      console.log('  trash icon not visible after hover');
    }
  }

  // ── /dwg-takeoff DrawingFilmstrip ─────────────────────────────────
  console.log('\n/dwg-takeoff — clicking second drawing card');
  await page.goto(`${FRONTEND}/dwg-takeoff`);
  await page.waitForLoadState('networkidle').catch(() => null);
  await page.waitForTimeout(2000);

  const dwgCards = page.locator('[data-testid="dwg-filmstrip-card"]');
  const dwgCount = await dwgCards.count();
  console.log(`  found ${dwgCount} DrawingFilmstrip cards`);

  if (dwgCount >= 2) {
    const tag = await dwgCards.nth(0).evaluate((el) => el.tagName);
    console.log(`  card tag: ${tag} (expect DIV after refactor)`);

    const before = await dwgCards.nth(1).evaluate((el) =>
      el.className.includes('border-blue-500/80') ? 'active' : 'inactive',
    );
    await dwgCards.nth(1).click();
    await page.waitForTimeout(800);
    const after = await dwgCards.nth(1).evaluate((el) =>
      el.className.includes('border-blue-500/80') ? 'active' : 'inactive',
    );
    console.log(`  state before: ${before}, after: ${after}`);
    if (before !== 'active' && after === 'active') {
      console.log('  ✓ click selected the drawing');
    } else {
      console.log('  state did not change as expected (may already have been active)');
    }
  } else {
    console.log('  (not enough drawings in dev DB to test)');
  }

  await browser.close();

  console.log(`\nConsole errors: ${errors.length}`);
  errors.slice(0, 5).forEach((e) => console.log('  ', e.slice(0, 200)));
})().catch((e) => { console.error(e); process.exit(1); });
