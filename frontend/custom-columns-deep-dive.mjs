// Deep-dive Custom Columns dialog + Regional standards (GAEB/AVA preset).
// Walks through:
//   1. Open Custom Columns dialog on Berlin DIN 276 BOQ (has populated resources).
//   2. Screenshot baseline dialog.
//   3. Expand Regional standards, screenshot.
//   4. Apply GAEB / AVA preset.
//   5. Close dialog, screenshot grid (check column auto-fit + overflow).
//   6. Inspect derived column values via getRowData.
//   7. Cleanup: remove preset columns so the next iteration is clean.
import { chromium } from 'playwright';
import path from 'node:path';
import fs from 'node:fs';

const BASE = 'http://127.0.0.1:8090';
const API = `${BASE}/api/v1`;
const PROJECT_ID = '536558f5-e163-4e07-be68-7349c3d7759f';
const BOQ_ID = '3db25e40-72a8-4086-af3d-3c77f424a23b';
const SHOTS = path.resolve('qa-shots/custom-cols');
fs.mkdirSync(SHOTS, { recursive: true });

const log = (...a) => console.log('[cc-dive]', ...a);

async function login() {
  const r = await fetch(`${API}/users/auth/login/`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email: 'v19-e2e@openestimate.com', password: 'OpenEstimate2024!' }),
  });
  return (await r.json()).access_token;
}

async function clearPresetCols(token) {
  // Wipe ALL existing custom columns so each run starts identical.
  const r = await fetch(`${API}/boq/boqs/${BOQ_ID}/columns/`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) return;
  const cols = await r.json();
  for (const c of cols) {
    const dr = await fetch(`${API}/boq/boqs/${BOQ_ID}/columns/${c.name}`, {
      method: 'DELETE', headers: { Authorization: `Bearer ${token}` },
    });
    log(`  delete ${c.name} -> ${dr.status}`);
  }
}

(async () => {
  const token = await login();
  log('login ok');
  await clearPresetCols(token);
  log('cleared any leftover preset cols');

  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  const page = await ctx.newPage();

  const consoleErrors = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  const failed404 = [];
  page.on('response', (r) => { if (r.status() === 404 && r.url().includes('/api/')) failed404.push(`${r.status()} ${r.url()}`); });

  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(({ token, projectId }) => {
    localStorage.setItem('oe_access_token', token);
    localStorage.setItem('oe_active_project', JSON.stringify({ id: projectId, name: 'Wohnanlage Berlin-Mitte', boqId: null }));
    localStorage.setItem('oe_onboarding_completed', 'true');
    localStorage.setItem('oe_tour_completed', 'true');
  }, { token, projectId: PROJECT_ID });

  log('navigating to BOQ');
  await page.goto(`${BASE}/boq/${BOQ_ID}`, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(SHOTS, '01-grid-baseline.png'), fullPage: false });
  log('saved 01-grid-baseline.png');

  // Open Custom Columns: Grid Settings button → Manage Columns menuitem.
  log('clicking Grid Settings button');
  await page.getByRole('button', { name: /grid settings/i }).first().click();
  await page.waitForTimeout(300);
  await page.getByRole('menuitem', { name: /manage columns/i }).first().click();
  log('opened Custom Columns dialog');

  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(SHOTS, '02-dialog-open.png'), fullPage: false });
  log('saved 02-dialog-open.png');

  // Expand Regional standards <details>.
  const regionalBtn = page.locator('summary', { hasText: /regional standards/i });
  if (await regionalBtn.isVisible().catch(() => false)) {
    await regionalBtn.click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SHOTS, '03-regional-expanded.png'), fullPage: false });
    log('saved 03-regional-expanded.png');
  } else {
    log('Regional standards summary not found');
  }

  // Apply GAEB / AVA preset.
  const gaebBtn = page.getByRole('button', { name: /GAEB.*AVA/i }).first();
  if (await gaebBtn.isVisible().catch(() => false)) {
    await gaebBtn.click();
    await page.waitForTimeout(2500); // mutations
    await page.screenshot({ path: path.join(SHOTS, '04-after-apply.png'), fullPage: false });
    log('saved 04-after-apply.png');
  } else {
    log('GAEB preset card not found');
  }

  // Close the dialog (look for close button or click backdrop).
  const closeBtn = page.locator('[aria-label="Close" i], [aria-label="Закрыть" i], [aria-label*="close" i]').first();
  if (await closeBtn.isVisible().catch(() => false)) {
    await closeBtn.click();
  } else {
    await page.keyboard.press('Escape');
  }
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(SHOTS, '05-grid-with-cols.png'), fullPage: false });
  log('saved 05-grid-with-cols.png');

  // Inspect grid: column widths, scroll overflow, sample row values.
  const gridInfo = await page.evaluate(() => {
    const root = document.querySelector('.ag-root-wrapper, [class*="ag-root"]');
    if (!root) return { error: 'AG Grid not found' };
    const headers = Array.from(root.querySelectorAll('.ag-header-cell')).map((h) => ({
      colId: h.getAttribute('col-id'),
      width: h.getBoundingClientRect().width,
      label: h.querySelector('.ag-header-cell-text')?.textContent?.trim(),
    }));
    const viewport = root.querySelector('.ag-center-cols-viewport');
    const overflow = viewport ? {
      scrollWidth: viewport.scrollWidth,
      clientWidth: viewport.clientWidth,
      hasOverflow: viewport.scrollWidth > viewport.clientWidth + 1,
    } : null;
    // Sample first 3 data rows' cells for derived columns.
    const rows = Array.from(root.querySelectorAll('.ag-center-cols-container .ag-row')).slice(0, 3);
    const sample = rows.map((r) => Array.from(r.querySelectorAll('.ag-cell')).map((c) => ({
      colId: c.getAttribute('col-id'),
      text: c.textContent?.trim()?.slice(0, 30),
    })).filter((c) => c.colId?.startsWith('custom_')));
    return { headers, overflow, sample };
  });
  log('grid info:', JSON.stringify(gridInfo, null, 2));

  // Cleanup so re-runs are deterministic.
  await clearPresetCols(token);
  log('cleanup ok');

  // Report.
  console.log('\n=== REPORT ===');
  console.log('console errors:', consoleErrors.length);
  if (consoleErrors.length) console.log(consoleErrors.slice(0, 5).join('\n'));
  console.log('404s:', failed404.length);
  if (failed404.length) console.log(failed404.slice(0, 5).join('\n'));
  console.log('overflow:', gridInfo.overflow);
  console.log('custom columns added:', (gridInfo.headers ?? []).filter((h) => h.colId?.startsWith('custom_')).length);
  console.log('column widths (custom only):', (gridInfo.headers ?? []).filter((h) => h.colId?.startsWith('custom_')).map((h) => `${h.label}=${Math.round(h.width)}`).join(', '));
  console.log('sample rows derived values:', JSON.stringify(gridInfo.sample, null, 2));

  await browser.close();
})().catch((e) => { console.error('FATAL:', e); process.exit(1); });
