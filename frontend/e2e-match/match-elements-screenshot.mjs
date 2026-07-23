import { chromium } from 'playwright';

const FRONTEND = 'http://localhost:5180';
const BACKEND = 'http://localhost:8000';
const USER = { email: 'v19-e2e@openestimate.com', password: 'OpenEstimate2024!' };

(async () => {
  const r = await fetch(`${BACKEND}/api/v1/users/auth/login/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: USER.email, password: USER.password }),
  });
  const t = await r.json();
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.goto(`${FRONTEND}/about`);
  await page.evaluate(({ access, refresh, email }) => {
    localStorage.setItem('oe_access_token', access);
    localStorage.setItem('oe_refresh_token', refresh);
    localStorage.setItem('oe_user_email', email);
    localStorage.setItem('oe_update_dismissed_version', '99.99.99');
    localStorage.setItem('oe_onboarding_completed', 'true');
    localStorage.setItem('oe_first_run', '0');
  }, { access: t.access_token, refresh: t.refresh_token ?? t.access_token, email: USER.email });
  await page.goto(`${FRONTEND}/match-elements`, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => null);
  await page.waitForTimeout(2000);
  await page.screenshot({ path: 'e2e-match/match-elements.png', fullPage: true });

  const visibleText = await page.evaluate(() => document.body.innerText);
  console.log('--- visible text ---');
  console.log(visibleText.slice(0, 3000));

  await browser.close();
})();
