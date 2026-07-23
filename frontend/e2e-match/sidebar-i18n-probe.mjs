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
  for (const lang of ['de', 'ru', 'en']) {
    const browser = await chromium.launch({ headless: true });
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    await page.goto(`${FRONTEND}/about`);
    await page.evaluate(({ access, refresh, email, lng }) => {
      localStorage.setItem('oe_access_token', access);
      localStorage.setItem('oe_refresh_token', refresh);
      localStorage.setItem('oe_user_email', email);
      localStorage.setItem('oe_update_dismissed_version', '99.99.99');
      localStorage.setItem('oe_onboarding_completed', 'true');
      localStorage.setItem('oe_first_run', '0');
      localStorage.setItem('i18nextLng', lng);
    }, { access: t.access_token, refresh: t.refresh_token ?? t.access_token, email: USER.email, lng: lang });
    await page.goto(`${FRONTEND}/dashboard`, { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => null);
    await page.waitForTimeout(2500);
    const labels = await page.evaluate(() => {
      const aside = document.querySelector('aside') || document.querySelector('nav');
      if (!aside) return null;
      const links = Array.from(aside.querySelectorAll('a, button'))
        .map((el) => el.textContent?.trim().split('\n')[0]?.trim() ?? '')
        .filter((s) => s && s.length < 50)
        .slice(0, 12);
      return links;
    });
    console.log(`[${lang}]`, JSON.stringify(labels));
    await browser.close();
  }
})().catch((e) => { console.error(e); process.exit(1); });
