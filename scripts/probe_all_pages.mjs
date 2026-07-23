// Headless multi-page smoke probe for OpenConstructionERP dev frontend.
// Logs in once as demo, injects token + skip-tour flags, then walks every
// route, captures status/console/page errors and a few content heuristics,
// and prints a summary table.
import { chromium } from 'playwright';

const FRONTEND = 'http://localhost:5180';
const BACKEND  = 'http://localhost:8000';
const EMAIL    = 'demo@openconstructionerp.com';
const PASSWORD = 'DemoPass1234!';

const ROUTES = [
  '/',
  '/projects',
  '/boq',
  '/costs',
  '/catalog',
  '/takeoff',
  '/dwg-takeoff',
  '/bim',
  '/match-elements',
  '/reports',
  '/reporting',
  '/finance',
  '/procurement',
  '/tendering',
  '/changeorders',
  '/risks',
  '/schedule',
  '/tasks',
  '/5d',
  '/files',
  '/photos',
  '/markups',
  '/field-reports',
  '/validation',
  '/inspections',
  '/safety',
  '/punchlist',
  '/assets',
  '/cde',
  '/meetings',
  '/transmittals',
  '/submittals',
  '/correspondence',
  '/rfi',
  '/chat',
  '/ai/quick-estimate',
  '/settings',
  '/modules',
  '/users',
  '/analytics',
  '/dashboards',
  '/weather',
  '/bim/rules',
];

console.log('logging in...');
const loginRes = await fetch(`${BACKEND}/api/v1/users/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
});
const loginJson = await loginRes.json();
const token = loginJson.access_token;
if (!token) {
  console.error('login failed:', loginJson);
  process.exit(1);
}
console.log('token acquired');

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext();
await ctx.addInitScript((tok) => {
  window.localStorage.setItem('oe_remember', '1');
  window.localStorage.setItem('oe_access_token', tok);
  window.localStorage.setItem('oe_user_email', 'demo@openconstructionerp.com');
  window.localStorage.setItem('oe_tour_completed', 'true');
  window.localStorage.setItem('oe_onboarding_completed', 'true');
  window.localStorage.setItem('oe_skip_tour', '1');
}, token);

const results = [];

for (const route of ROUTES) {
  const page = await ctx.newPage();
  const consoleErrors = [];
  const pageErrors = [];
  let mainStatus = null;

  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text());
  });
  page.on('pageerror', (e) => pageErrors.push(e.message || String(e)));
  page.on('response', (r) => {
    try {
      if (mainStatus === null && r.url().startsWith(FRONTEND) && r.request().resourceType() === 'document') {
        mainStatus = r.status();
      }
    } catch {}
  });

  let navError = null;
  try {
    await page.goto(`${FRONTEND}${route}`, { waitUntil: 'networkidle', timeout: 20000 });
  } catch (e) {
    navError = e.message;
  }
  await page.waitForTimeout(2500);

  let bodyText = '';
  let h1Count = 0;
  let buttonCount = 0;
  let mainHtmlLen = 0;
  let url = '';
  try {
    bodyText = await page.locator('body').innerText({ timeout: 2000 });
  } catch {}
  try {
    h1Count = await page.locator('h1').count();
  } catch {}
  try {
    buttonCount = await page.locator('button').count();
  } catch {}
  try {
    mainHtmlLen = (await page.locator('main').first().innerHTML({ timeout: 1500 }).catch(() => '')).length;
  } catch {}
  try {
    url = page.url();
  } catch {}

  const lower = bodyText.toLowerCase();
  const empties = [];
  if (/select a project/i.test(bodyText)) empties.push('select-a-project');
  if (/no projects available/i.test(bodyText)) empties.push('no-projects');
  if (/something went wrong/i.test(bodyText)) empties.push('error-boundary');
  if (/page not found|404/i.test(bodyText) && bodyText.length < 400) empties.push('404');
  // spinner only — small body, no h1, no buttons
  const spinnerOnly = bodyText.trim().length < 40 && h1Count === 0 && buttonCount < 2;

  const totalErrors = consoleErrors.length + pageErrors.length;
  let status = 'OK';
  let reason = '';
  if (navError) {
    status = 'BLANK';
    reason = `nav error: ${navError.split('\n')[0].slice(0, 120)}`;
  } else if (mainStatus && mainStatus >= 500) {
    status = 'BLANK';
    reason = `http ${mainStatus}`;
  } else if (pageErrors.length > 0) {
    status = 'BLANK';
    reason = `pageerror: ${pageErrors[0].slice(0, 140)}`;
  } else if (spinnerOnly) {
    status = 'BLANK';
    reason = `spinner-only (body=${bodyText.trim().length} chars, h1=${h1Count})`;
  } else if (bodyText.trim().length < 80) {
    status = 'BLANK';
    reason = `near-empty body (${bodyText.trim().length} chars)`;
  } else if (empties.length > 0 && bodyText.trim().length < 600) {
    status = 'PARTIAL';
    reason = `empty-state: ${empties.join(',')}`;
  } else if (totalErrors >= 5) {
    status = 'PARTIAL';
    reason = `${consoleErrors.length} console errors, ${pageErrors.length} page errors`;
  } else if (h1Count === 0 && bodyText.trim().length < 200) {
    status = 'PARTIAL';
    reason = `no h1, short body (${bodyText.trim().length} chars)`;
  } else if (totalErrors > 0) {
    status = 'OK';
    reason = `${totalErrors} non-fatal err(s); body=${bodyText.trim().length}`;
  } else {
    reason = `body=${bodyText.trim().length} chars, h1=${h1Count}, btn=${buttonCount}`;
  }

  // route equivalence
  const finalRoute = url.replace(FRONTEND, '');
  const redirected = finalRoute && finalRoute !== route && !(route === '/' && finalRoute === '/');

  results.push({
    route,
    status,
    reason,
    httpStatus: mainStatus,
    bodyLen: bodyText.trim().length,
    h1: h1Count,
    btn: buttonCount,
    mainLen: mainHtmlLen,
    consoleErr: consoleErrors.length,
    pageErr: pageErrors.length,
    pageErrFirst: pageErrors[0]?.slice(0, 200) || '',
    consoleErrFirst: consoleErrors[0]?.slice(0, 200) || '',
    redirectedTo: redirected ? finalRoute : '',
    empties,
  });

  console.log(
    `[${status.padEnd(7)}] ${route.padEnd(22)} http=${mainStatus} body=${bodyText.trim().length} h1=${h1Count} btn=${buttonCount} cErr=${consoleErrors.length} pErr=${pageErrors.length}${redirected ? ' →' + finalRoute : ''}`
  );

  await page.close();
}

await browser.close();

// markdown table
console.log('\n\n=== MARKDOWN TABLE ===\n');
console.log('| Route | Status | Reason |');
console.log('|---|---|---|');
for (const r of results) {
  const icon = r.status === 'OK' ? 'OK' : r.status === 'PARTIAL' ? 'PARTIAL' : 'BLANK';
  const note = r.redirectedTo ? `${r.reason} (→${r.redirectedTo})` : r.reason;
  console.log(`| \`${r.route}\` | ${icon} | ${note.replace(/\|/g, '\\|')} |`);
}

console.log('\n\n=== BLANK DETAILS ===\n');
for (const r of results.filter((x) => x.status === 'BLANK')) {
  console.log(`\n--- ${r.route} ---`);
  console.log(`http=${r.httpStatus} body=${r.bodyLen} h1=${r.h1} btn=${r.btn} mainLen=${r.mainLen}`);
  if (r.pageErrFirst) console.log(`pageerror: ${r.pageErrFirst}`);
  if (r.consoleErrFirst) console.log(`console:   ${r.consoleErrFirst}`);
  if (r.redirectedTo) console.log(`redirected to: ${r.redirectedTo}`);
}

console.log('\n\n=== PARTIAL DETAILS ===\n');
for (const r of results.filter((x) => x.status === 'PARTIAL')) {
  console.log(`\n--- ${r.route} ---`);
  console.log(`body=${r.bodyLen} h1=${r.h1} btn=${r.btn} cErr=${r.consoleErr} pErr=${r.pageErr}`);
  if (r.pageErrFirst) console.log(`pageerror: ${r.pageErrFirst}`);
  if (r.consoleErrFirst) console.log(`console:   ${r.consoleErrFirst}`);
}

const okN = results.filter((r) => r.status === 'OK').length;
const partialN = results.filter((r) => r.status === 'PARTIAL').length;
const blankN = results.filter((r) => r.status === 'BLANK').length;
console.log(`\n\nSUMMARY: ${okN} OK / ${partialN} PARTIAL / ${blankN} BLANK / ${results.length} total`);
