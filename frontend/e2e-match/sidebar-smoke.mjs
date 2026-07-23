// Sidebar smoke pass — visits every primary route, captures any 4xx/5xx
// network error or console error per page. Used during Wave 5 audit.

import { chromium } from 'playwright';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const __dirname_esm = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(__dirname_esm, '../../qa-tests/_sidebar-smoke');
fs.mkdirSync(OUT, { recursive: true });

const FRONTEND = 'http://localhost:5180';
const BACKEND = 'http://localhost:8000';
const USER = { email: 'v19-e2e@openestimate.com', password: 'OpenEstimate2024!' };

// Stable list of primary routes — keep aligned with sidebar groups.
const ROUTES = [
  '/',
  '/projects',
  '/dashboard',
  '/boq',
  '/costs',
  '/match-elements',
  '/bim',
  '/dwg-takeoff',
  '/takeoff',
  '/quantities',
  '/files',
  '/cde',
  '/photos',
  '/markups',
  '/field-reports',
  '/schedule',
  '/tasks',
  '/risks',
  '/finance',
  '/budget',
  '/evm',
  '/procurement',
  '/changeorders',
  '/contacts',
  '/meetings',
  '/rfi',
  '/submittals',
  '/correspondence',
  '/reports',
  '/inspections',
  '/punchlist',
  '/safety',
  '/ncr',
  '/integrations',
  '/users',
  '/settings',
];

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
  const access = t.access_token;
  const refresh = t.refresh_token ?? access;
  console.log('✓ login');

  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  // Per-route accumulators. Reset on goto.
  const findings = [];
  let cur = null;

  page.on('console', (m) => {
    if (m.type() === 'error' && cur) {
      cur.console.push(m.text().slice(0, 200));
    }
  });
  page.on('response', (r) => {
    const url = r.url();
    if (cur && r.status() >= 400) {
      // Capture ALL non-2xx responses so we don't miss external 400s.
      cur.network.push(`${r.status()} ${r.request().method()} ${url}`);
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

  for (const route of ROUTES) {
    cur = { route, console: [], network: [] };
    try {
      const resp = await page.goto(`${FRONTEND}${route}`, { waitUntil: 'domcontentloaded', timeout: 30000 });
      cur.status = resp ? resp.status() : 'no-resp';
      // Let SPA finish initial fetches
      await page.waitForLoadState('networkidle', { timeout: 12000 }).catch(() => null);
      await page.waitForTimeout(400);
    } catch (e) {
      cur.error = e.message.slice(0, 200);
    }
    findings.push(cur);
    const cN = cur.console.length, nN = cur.network.length;
    const flag = cN || nN ? `⚠ ${cN}c ${nN}n` : '✓';
    console.log(`  ${flag.padEnd(7)} ${route}`);
  }

  await browser.close();

  fs.writeFileSync(path.join(OUT, 'findings.json'), JSON.stringify(findings, null, 2));

  console.log('\n=== ISSUES ===');
  for (const f of findings) {
    if (f.console.length || f.network.length) {
      console.log(`\n${f.route}`);
      for (const c of f.console.slice(0, 3)) console.log(`  console: ${c}`);
      for (const n of f.network.slice(0, 5)) console.log(`  network: ${n}`);
    }
  }
  console.log(`\nFull JSON: ${OUT}/findings.json`);
})().catch((e) => {
  console.error('SMOKE ERROR:', e);
  process.exit(1);
});
