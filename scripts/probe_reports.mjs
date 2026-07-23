// Headless probe of /reports — captures console errors, network errors, and the
// rendered DOM so we can see exactly what the user sees. Logs in as demo first
// so the page has projects to render.
import { chromium } from 'playwright';

const FRONTEND = 'http://localhost:5180';
const BACKEND  = 'http://localhost:8000';
const EMAIL    = 'demo@openconstructionerp.com';
const PASSWORD = 'DemoPass1234!';

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext();
const page = await ctx.newPage();

const consoleEvents = [];
page.on('console', (m) => consoleEvents.push(`[${m.type()}] ${m.text()}`));
page.on('pageerror', (e) => consoleEvents.push(`[pageerror] ${e.message}`));

const requests = [];
page.on('response', (r) => {
  if (r.url().includes('/api/v1/')) requests.push(`${r.status()} ${r.request().method()} ${r.url()}`);
});

// Pre-set the auth token via fetch call before nav.
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

await page.addInitScript((tok) => {
  // useAuthStore reads `oe_access_token` from localStorage when remember=true.
  window.localStorage.setItem('oe_remember', '1');
  window.localStorage.setItem('oe_access_token', tok);
  window.localStorage.setItem('oe_user_email', 'demo@openconstructionerp.com');
  // Skip onboarding tour
  window.localStorage.setItem('oe_tour_completed', 'true');
  window.localStorage.setItem('oe_onboarding_completed', 'true');
  window.localStorage.setItem('oe_skip_tour', '1');
}, token);

console.log('navigating to /reports...');
await page.goto(`${FRONTEND}/reports`, { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForTimeout(2500);

const dom = await page.locator('main').innerHTML().catch(() => '<no main>');
const visibleText = await page.locator('body').innerText().catch(() => '');
const cardsCount = await page.locator('[class*="grid-cols"] > div').count().catch(() => -1);

console.log('\n=== console events ===');
consoleEvents.slice(0, 50).forEach((l) => console.log(l));
console.log('\n=== api requests ===');
requests.slice(0, 30).forEach((l) => console.log(l));
console.log('\n=== cards count ===', cardsCount);
console.log('\n=== full main innerHTML ===');
console.log(dom);

await browser.close();
