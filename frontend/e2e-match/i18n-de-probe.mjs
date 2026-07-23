import { chromium } from 'playwright';

const FRONTEND = 'http://localhost:5180';
const BACKEND = 'http://localhost:8000';
const USER = { email: 'v19-e2e@openestimate.com', password: 'OpenEstimate2024!' };

const EXPECTED_H1 = {
  en: 'Match Elements',
  de: 'Elemente zuordnen',
  ru: 'Сопоставление элементов',
};

async function login() {
  const r = await fetch(`${BACKEND}/api/v1/users/auth/login/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: USER.email, password: USER.password }),
  });
  return r.json();
}

async function probe(lang, t) {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  await page.goto(`${FRONTEND}/about`);
  await page.evaluate(
    ({ access, refresh, email, lng }) => {
      localStorage.setItem('oe_access_token', access);
      localStorage.setItem('oe_refresh_token', refresh);
      localStorage.setItem('oe_user_email', email);
      localStorage.setItem('oe_update_dismissed_version', '99.99.99');
      localStorage.setItem('oe_onboarding_completed', 'true');
      localStorage.setItem('oe_first_run', '0');
      localStorage.setItem('i18nextLng', lng);
    },
    { access: t.access_token, refresh: t.refresh_token ?? t.access_token, email: USER.email, lng: lang },
  );
  await page.goto(`${FRONTEND}/match-elements`, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => null);
  await page.waitForTimeout(2500);

  const titles = await page.evaluate(() => {
    const headerH1 = document.querySelector('header h1')?.textContent?.trim() ?? null;
    const pageH1 = document.querySelector('main h1, [data-page-title], section h1')?.textContent?.trim() ?? null;
    const allH1 = Array.from(document.querySelectorAll('h1')).map((el) => ({
      parent: el.parentElement?.tagName ?? null,
      inHeader: !!el.closest('header'),
      text: el.textContent?.trim().slice(0, 80) ?? null,
    }));
    return { headerH1, pageH1, allH1 };
  });

  const expected = EXPECTED_H1[lang];
  const ok = titles.headerH1 === expected;
  console.log(`[${lang}] expected="${expected}" headerH1="${titles.headerH1}" ${ok ? '✓' : '✗ FAIL'}`);
  console.log(`[${lang}] all h1s:`, JSON.stringify(titles.allH1));

  await browser.close();
  return ok;
}

(async () => {
  const t = await login();
  const results = await Promise.all([probe('en', t), probe('de', t), probe('ru', t)]);
  const allPass = results.every(Boolean);
  console.log(allPass ? '\nAll H1 translations correct ✓' : '\nFAIL — some H1s did not translate ✗');
  process.exit(allPass ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(1); });
