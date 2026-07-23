// Quick screenshot of dashboard hero to verify the 'Developed by' label.
import { chromium } from 'playwright';
import path from 'node:path';

const BASE = 'http://127.0.0.1:8090';
const API = `${BASE}/api/v1`;

async function login() {
  const r = await fetch(`${API}/users/auth/login/`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email: 'v19-e2e@openestimate.com', password: 'OpenEstimate2024!' }),
  });
  return (await r.json()).access_token;
}

(async () => {
  const token = await login();
  const projects = await (await fetch(`${API}/projects/`, { headers: { Authorization: `Bearer ${token}` } })).json();
  const project = projects[0];

  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 600 } });
  const page = await ctx.newPage();

  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(({ token, project }) => {
    localStorage.setItem('oe_access_token', token);
    localStorage.setItem('oe_active_project', JSON.stringify({ id: project.id, name: project.name, boqId: null }));
    localStorage.setItem('oe_onboarding_completed', 'true');
    localStorage.setItem('oe_tour_completed', 'true');
  }, { token, project });

  page.on('response', (r) => {
    const u = r.url();
    if (u.includes('ddc-logo')) console.log(`logo response: ${r.status()} ${u}`);
  });
  page.on('requestfailed', (r) => {
    if (r.url().includes('ddc-logo')) console.log(`logo FAILED: ${r.url()} reason=${r.failure()?.errorText}`);
  });
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  const dim = await page.locator('img[alt="DataDrivenConstruction"]').evaluate((el) => ({
    natW: el.naturalWidth, natH: el.naturalHeight, complete: el.complete, src: el.currentSrc,
  })).catch(() => null);
  console.log('img dimensions:', JSON.stringify(dim));
  await page.screenshot({ path: path.resolve('qa-shots/developed-by.png'), fullPage: false });
  await browser.close();
  console.log('saved qa-shots/developed-by.png');
})().catch((e) => { console.error('FATAL:', e); process.exit(1); });
