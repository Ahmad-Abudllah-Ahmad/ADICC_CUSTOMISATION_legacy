import { chromium } from 'playwright';

const FRONTEND = 'http://localhost:5180';
const BACKEND = 'http://localhost:8000';
const USER = { email: 'v19-e2e@openestimate.com', password: 'OpenEstimate2024!' };

const ROUTES = [
  '/dashboard', '/projects', '/boq', '/costs', '/match-elements',
  '/bim', '/dwg-takeoff', '/data-explorer', '/quantities', '/takeoff',
  '/assemblies', '/templates', '/files', '/photos', '/markups',
  '/schedule', '/tasks', '/risks', '/finance', '/budget', '/evm',
  '/procurement', '/changeorders', '/contacts', '/meetings', '/rfi',
  '/submittals', '/correspondence', '/reports', '/inspections',
  '/punchlist', '/safety', '/ncr', '/integrations', '/users', '/settings',
  '/validation', '/sustainability', '/ai-estimate', '/requirements',
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

  const dupReport = [];
  for (const route of ROUTES) {
    const seen = new Map();
    const onResponse = (r) => {
      const url = r.url();
      if (!url.includes('/api/')) return;
      const idx = url.indexOf('/api/');
      const path = url.slice(idx);
      const method = r.request().method();
      // Keep query string — different params (?limit=, ?project_id=…) are
      // genuinely different requests; conflating them produces noise.
      // Strip volatile cache-bust tokens (?_t=…, &token=…) before keying.
      const cleaned = path.replace(/[?&]_t=[^&]*/g, '').replace(/[?&]token=[^&]*/g, '');
      const key = `${method} ${cleaned}`;
      seen.set(key, (seen.get(key) || 0) + 1);
    };
    page.on('response', onResponse);
    try {
      await page.goto(`${FRONTEND}${route}`, { waitUntil: 'domcontentloaded', timeout: 20000 });
      await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => null);
      await page.waitForTimeout(800);
    } catch {}
    page.off('response', onResponse);
    const dups = [...seen.entries()].filter(([_, n]) => n > 1).map(([k, n]) => `${n}x ${k}`);
    if (dups.length) dupReport.push({ route, dups });
  }

  console.log('\nDuplicate-fetch findings:');
  for (const r of dupReport) {
    console.log(`\n${r.route}`);
    for (const d of r.dups) console.log(`  ${d}`);
  }
  console.log(`\n${dupReport.length} routes with duplicate fetches`);
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
