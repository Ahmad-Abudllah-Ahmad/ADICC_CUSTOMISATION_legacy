// Perf probe — visit a few heavy pages and measure (a) total backend
// requests, (b) cumulative response size, (c) any duplicate URLs hit.

import { chromium } from 'playwright';

const FRONTEND = 'http://localhost:5180';
const BACKEND = 'http://localhost:8000';
const USER = { email: 'v19-e2e@openestimate.com', password: 'OpenEstimate2024!' };

const ROUTES = ['/projects', '/boq', '/bim', '/finance', '/reports'];

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

(async () => {
  const t = await login();
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

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

  for (const route of ROUTES) {
    const reqs = [];
    let bytes = 0;
    const seen = new Map();

    const onResponse = async (r) => {
      const url = r.url();
      // Vite dev server proxies /api/* — match by path, not host.
      if (!url.includes('/api/')) return;
      const len = parseInt(r.headers()['content-length'] || '0', 10);
      const idx = url.indexOf('/api/');
      const path = url.slice(idx);
      const method = r.request().method();
      // Key duplicates by METHOD+PATH so HEAD vs GET on the same URL
      // don't get falsely flagged as duplicates of each other (the BIM
      // geometry loader does both — content-type sniff then download).
      const key = `${method} ${path}`;
      reqs.push({ path, method, status: r.status(), len });
      bytes += isNaN(len) ? 0 : len;
      seen.set(key, (seen.get(key) || 0) + 1);
    };
    page.on('response', onResponse);

    const t0 = Date.now();
    await page.goto(`${FRONTEND}${route}`, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => null);
    const took = Date.now() - t0;

    page.off('response', onResponse);

    const duplicates = [...seen.entries()].filter(([_, n]) => n > 1).sort((a, b) => b[1] - a[1]);
    const slow = reqs.filter((r) => r.status >= 400 || r.len > 50000).sort((a, b) => b.len - a.len);

    console.log(`\n${route}  ${took}ms  ${reqs.length} requests  ${(bytes / 1024).toFixed(1)} KB`);
    if (duplicates.length) {
      console.log('  duplicates (same URL fetched N times this page):');
      for (const [p, n] of duplicates.slice(0, 5)) console.log(`    ${n}x  ${p}`);
    }
    if (slow.length) {
      console.log('  largest / errors:');
      // HEAD responses surface content-length headers without a body — they
      // look identical to a same-URL GET in size-only output but transfer
      // ~0 bytes. Label the method so the duplicate isn't mistaken for an
      // actual second download.
      for (const r of slow.slice(0, 5))
        console.log(`    ${r.method.padEnd(4)}  ${r.status}  ${(r.len / 1024).toFixed(1)} KB  ${r.path}`);
    }
  }

  await browser.close();
})();
