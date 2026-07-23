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

  const geometryFetches = [];
  page.on('request', (r) => {
    if (r.url().includes('/bim_hub/models/') && r.url().includes('/geometry/')) {
      geometryFetches.push({ method: r.method(), url: r.url().slice(0, 110) });
    }
  });

  await page.goto(`${FRONTEND}/about`);
  await page.evaluate(({ access, refresh, email }) => {
    localStorage.setItem('oe_access_token', access);
    localStorage.setItem('oe_refresh_token', refresh);
    localStorage.setItem('oe_user_email', email);
    localStorage.setItem('oe_update_dismissed_version', '99.99.99');
    localStorage.setItem('oe_onboarding_completed', 'true');
    localStorage.setItem('oe_first_run', '0');
  }, { access: t.access_token, refresh: t.refresh_token ?? t.access_token, email: USER.email });

  await page.goto(`${FRONTEND}/bim`, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => null);
  await page.waitForTimeout(2000);

  const byUrl = {};
  for (const f of geometryFetches) {
    const k = `${f.method} ${f.url}`;
    byUrl[k] = (byUrl[k] || 0) + 1;
  }
  console.log('geometry fetches:');
  for (const [k, n] of Object.entries(byUrl)) console.log(`  ${n}x ${k}`);

  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
