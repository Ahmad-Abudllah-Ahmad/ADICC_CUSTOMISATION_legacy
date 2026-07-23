import { chromium } from 'playwright';

const FRONTEND = 'http://localhost:5180';
const BACKEND = 'http://localhost:8000';
const USER = { email: 'v19-e2e@openestimate.com', password: 'OpenEstimate2024!' };

const ROUTES = [
  '/assemblies',
  '/requirements',
  '/sustainability',
  '/cad-explorer',
  '/quantities',
  '/ai-estimate',
  '/ai-advisor',
  '/integrations',
  '/templates',
  '/resource-catalog',
  '/validation',
  '/photos',
  '/markups',
  '/inspections',
  '/punchlist',
  '/safety',
  '/ncr',
];

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

  const results = [];
  for (const route of ROUTES) {
    const page = await ctx.newPage();
    const consoleErrors = [];
    const networkFails = [];
    page.on('console', (m) => {
      if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 250));
    });
    page.on('response', (r) => {
      if (r.status() >= 400) networkFails.push(`${r.status()} ${r.url().slice(0, 120)}`);
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

    const start = Date.now();
    try {
      await page.goto(`${FRONTEND}${route}`, { waitUntil: 'domcontentloaded' });
      await page.waitForLoadState('networkidle').catch(() => null);
      await page.waitForTimeout(1500);
    } catch (e) {
      results.push({ route, error: e.message, time: Date.now() - start });
      await page.close();
      continue;
    }
    const elapsed = Date.now() - start;

    const probe = await page.evaluate(() => {
      const h1 = document.querySelector('h1')?.textContent?.trim()?.slice(0, 80) ?? null;
      const buttonsCount = document.querySelectorAll('button:not([disabled])').length;
      const linksCount = document.querySelectorAll('a[href]').length;
      const inputsCount = document.querySelectorAll('input, select, textarea').length;
      const errorBanner = Array.from(document.querySelectorAll('[role="alert"], .text-red-500, .bg-red-50, .text-error'))
        .map((el) => el.textContent?.trim().slice(0, 100))
        .filter(Boolean)
        .slice(0, 3);
      const bodyText = document.body.textContent ?? '';
      const hasError = bodyText.includes('Something went wrong') || bodyText.includes('Application error') || bodyText.includes('Page not found');
      return { h1, buttonsCount, linksCount, inputsCount, errorBanner, hasError };
    });

    results.push({ route, time: elapsed, ...probe, console: consoleErrors, networkFails });
    await page.close();
  }

  await browser.close();
  console.log(JSON.stringify(results, null, 2));
})().catch((e) => { console.error(e); process.exit(1); });
