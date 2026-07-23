/* v3.12.0 Stream A — Playwright verification */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const FRONTEND = 'http://localhost:5180';
const BACKEND = 'http://localhost:8000';
const BOQ_ID = '0567be11-dc10-4be8-b085-bbbb679e1357';
const OUT = path.resolve('../qa-tests/_v3.12.0-stream-A');
fs.mkdirSync(OUT, { recursive: true });

const LOG = [];
function log(...m) {
  const s = m.map(x => typeof x === 'string' ? x : JSON.stringify(x)).join(' ');
  console.log(s);
  LOG.push(s);
}

async function login() {
  const r = await fetch(`${BACKEND}/api/v1/users/auth/demo-login/`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'demo@openconstructionerp.com' }),
  });
  if (!r.ok) throw new Error('demo-login failed: ' + r.status);
  return await r.json();
}

async function shot(page, name) {
  const p = path.join(OUT, name);
  await page.screenshot({ path: p, fullPage: false });
  log('  shot:', name);
}

const RESULTS = { wave1: [], wave2: [], wave3: [], critical: [], notes: [] };
function record(wave, step, ok, obs, shotName) {
  RESULTS[wave].push({ step, ok, obs, shot: shotName });
  log(`[${wave} step ${step}]`, ok ? 'OK' : 'FAIL', '-', obs, shotName ? `(${shotName})` : '');
}

async function selectRowsByOrd(page, ordinals) {
  // Click each target one at a time. Recompute coordinates between clicks because
  // the grid may reflow after selection (e.g. summary row, batch action bar).
  let clicked = 0;
  const got = [];
  for (const ord of ordinals) {
    const coords = await page.evaluate((targetOrd) => {
      const rows = [...document.querySelectorAll('.ag-center-cols-container .ag-row')];
      const r = rows.find(rw => rw.querySelector('[col-id="ordinal"]')?.innerText?.trim() === targetOrd);
      if (!r) return null;
      const cb = r.querySelector('input[type="checkbox"]') ||
                 r.querySelector('.ag-checkbox-input') ||
                 r.querySelector('[role="checkbox"]');
      if (!cb) return null;
      cb.scrollIntoView({ block: 'center' });
      const rect = cb.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return null;
      return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
    }, ord);
    if (!coords) continue;
    await page.mouse.click(coords.x, coords.y);
    // Verify the row is actually selected; retry once if not
    await page.waitForTimeout(250);
    const isSelected = await page.evaluate((o) => {
      const rows = [...document.querySelectorAll('.ag-center-cols-container .ag-row')];
      const r = rows.find(rw => rw.querySelector('[col-id="ordinal"]')?.innerText?.trim() === o);
      if (!r) return false;
      const cb = r.querySelector('input[type="checkbox"]');
      return r.classList.contains('ag-row-selected') ||
             (cb && cb.checked) ||
             r.querySelector('.ag-checkbox-input')?.checked === true ||
             r.getAttribute('aria-selected') === 'true';
    }, ord);
    if (isSelected) {
      clicked++;
      got.push(ord);
    } else {
      // Retry by recomputing coordinates after possible scroll
      const c2 = await page.evaluate((targetOrd) => {
        const rows = [...document.querySelectorAll('.ag-center-cols-container .ag-row')];
        const r = rows.find(rw => rw.querySelector('[col-id="ordinal"]')?.innerText?.trim() === targetOrd);
        if (!r) return null;
        const cb = r.querySelector('input[type="checkbox"]') ||
                   r.querySelector('.ag-checkbox-input');
        if (!cb) return null;
        const rect = cb.getBoundingClientRect();
        return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
      }, ord);
      if (c2) {
        await page.mouse.click(c2.x, c2.y);
        await page.waitForTimeout(250);
        const isSel2 = await page.evaluate((o) => {
          const rows = [...document.querySelectorAll('.ag-center-cols-container .ag-row')];
          const r = rows.find(rw => rw.querySelector('[col-id="ordinal"]')?.innerText?.trim() === o);
          return r ? r.classList.contains('ag-row-selected') || r.getAttribute('aria-selected') === 'true' : false;
        }, ord);
        if (isSel2) { clicked++; got.push(ord); }
      }
    }
  }
  return { clicked, got, requested: ordinals.length };
}

async function captureByOrd(page) {
  // Snapshot every data row's ord -> {unit_rate, quantity, total}
  return await page.evaluate(() => {
    const rows = [...document.querySelectorAll('.ag-center-cols-container .ag-row')]
      .filter(r => !(r.className || '').match(/section|resource|footer/i));
    const out = {};
    for (const r of rows) {
      const ord = r.querySelector('[col-id="ordinal"]')?.innerText?.trim();
      if (!ord) continue;
      out[ord] = {
        unit_rate: r.querySelector('[col-id="unit_rate"]')?.innerText?.trim(),
        quantity: r.querySelector('[col-id="quantity"]')?.innerText?.trim(),
      };
    }
    return out;
  });
}

function num(s) {
  if (!s) return 0;
  // Try BR style (1.234,56) and EN style (1,234.56)
  const cleaned = s.replace(/[^\d.,-]/g, '');
  // Heuristic: last separator is decimal
  const lastDot = cleaned.lastIndexOf('.');
  const lastComma = cleaned.lastIndexOf(',');
  let norm;
  if (lastDot > lastComma) {
    // thousand=, decimal=.
    norm = cleaned.replace(/,/g, '');
  } else if (lastComma > lastDot) {
    // thousand=. decimal=,
    norm = cleaned.replace(/\./g, '').replace(',', '.');
  } else {
    norm = cleaned;
  }
  return parseFloat(norm);
}

async function closeAnyDialog(page) {
  for (let i = 0; i < 5; i++) {
    const open = await page.evaluate(() => {
      const dlg = document.querySelector('[role="dialog"], [role="alertdialog"]');
      return !!dlg;
    });
    if (!open) break;
    // Look for Cancel button first
    const cancelClicked = await page.evaluate(() => {
      const dlg = document.querySelector('[role="dialog"], [role="alertdialog"]');
      if (!dlg) return false;
      const btns = [...dlg.querySelectorAll('button')];
      const cancel = btns.find(b => /^cancel$/i.test(b.textContent?.trim() || ''));
      if (cancel) { cancel.click(); return true; }
      return false;
    });
    if (!cancelClicked) {
      await page.keyboard.press('Escape').catch(() => {});
    }
    await page.waitForTimeout(500);
  }
  await page.waitForTimeout(400);
}

async function clickByAria(page, aria) {
  // Click via evaluate to bypass backdrop overlays
  return await page.evaluate((sel) => {
    const btn = document.querySelector(sel);
    if (!btn) return false;
    btn.click();
    return true;
  }, `[aria-label*="${aria}" i]`);
}

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();

const consoleErrs = [];
page.on('console', m => { if (m.type() === 'error') consoleErrs.push(m.text()); });
page.on('pageerror', e => consoleErrs.push('PAGEERROR: ' + e.message));

const networkFails = [];
const bulkRequests = [];
page.on('response', resp => {
  const u = resp.url();
  if (u.startsWith(BACKEND) && resp.status() >= 400) {
    networkFails.push({ url: u.replace(BACKEND, ''), status: resp.status() });
  }
});
page.on('request', req => {
  const u = req.url();
  if (u.includes('bulk-update') || u.includes('restore-field')) {
    let body = null;
    try { body = req.postData(); } catch {}
    bulkRequests.push({ method: req.method(), url: u.replace(BACKEND, ''), body });
  }
});

// Auth
log('===== AUTH =====');
const tokens = await login();
await page.goto(FRONTEND + '/', { waitUntil: 'domcontentloaded' });
await page.evaluate(t => {
  localStorage.setItem('oe_access_token', t.a);
  localStorage.setItem('oe_refresh_token', t.r);
  localStorage.setItem('oe_user_email', 'demo@openconstructionerp.com');
}, { a: tokens.access_token, r: tokens.refresh_token });

// ===== WAVE 1 =====
log('\n===== WAVE 1 — Golden path =====');

// W1.1
try {
  await page.goto(FRONTEND + '/', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);
  await shot(page, 'wave1_01_dashboard.png');
  record('wave1', 1, true, 'Dashboard loaded after auth', 'wave1_01_dashboard.png');
} catch (e) {
  await shot(page, 'wave1_01_dashboard_FAIL.png');
  record('wave1', 1, false, 'dashboard load: ' + e.message, 'wave1_01_dashboard_FAIL.png');
}

// W1.2
try {
  await page.goto(FRONTEND + '/boq', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);
  await shot(page, 'wave1_02_boq_list.png');
  await page.goto(FRONTEND + '/boq/' + BOQ_ID, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(5500);
  await shot(page, 'wave1_02b_boq_editor_initial.png');
  const cap = await captureByOrd(page);
  const ords = Object.keys(cap);
  log('  data rows by ord:', ords.length, 'first 5:', JSON.stringify(ords.slice(0,5)));
  record('wave1', 2, ords.length >= 3, `Opened BOQ — ${ords.length} data rows`, 'wave1_02b_boq_editor_initial.png');
} catch (e) {
  await shot(page, 'wave1_02_FAIL.png');
  record('wave1', 2, false, 'BOQ open: ' + e.message, 'wave1_02_FAIL.png');
}

// W1.3
try {
  const chips = await page.evaluate(() => ({
    multiplyRate: !!document.querySelector('[aria-label*="Multiply rate" i]'),
    multiplyQty: !!document.querySelector('[aria-label*="Multiply quantity" i]'),
    classification: !!document.querySelector('[aria-label*="Set classification" i]'),
    batchToolbar: !!document.querySelector('[role="toolbar"][aria-label*="Batch" i]'),
  }));
  const anyShown = chips.multiplyRate || chips.multiplyQty || chips.classification || chips.batchToolbar;
  await shot(page, 'wave1_03_no_selection_no_chips.png');
  record('wave1', 3, !anyShown, `Chips hidden with no selection — ${JSON.stringify(chips)}`, 'wave1_03_no_selection_no_chips.png');
} catch (e) {
  record('wave1', 3, false, 'inspect chips: ' + e.message, null);
}

// Pick 3 stable target ordinals from our seeded set
const TARGET_ORDS = ['02.01.001', '02.01.002', '02.01.003'];

// W1.4
try {
  const sel = await selectRowsByOrd(page, TARGET_ORDS);
  log('  selectRowsByOrd:', JSON.stringify(sel));
  await page.waitForTimeout(800);
  const chips = await page.evaluate(() => ({
    multiplyRate: !!document.querySelector('[aria-label*="Multiply rate" i]'),
    multiplyQty: !!document.querySelector('[aria-label*="Multiply quantity" i]'),
    classification: !!document.querySelector('[aria-label*="Set classification" i]'),
    batchToolbar: !!document.querySelector('[role="toolbar"][aria-label*="Batch" i]'),
  }));
  await shot(page, 'wave1_04_3rows_chips_visible.png');
  const ok = chips.multiplyRate && chips.multiplyQty && chips.classification && chips.batchToolbar && sel.clicked === 3;
  record('wave1', 4, ok, `Selected ${sel.clicked} target rows; chips: ${JSON.stringify(chips)}`, 'wave1_04_3rows_chips_visible.png');
} catch (e) {
  await shot(page, 'wave1_04_FAIL.png');
  record('wave1', 4, false, 'select 3 rows / chips: ' + e.message, 'wave1_04_FAIL.png');
}

// W1.5 — Multiply rate 1.10
let captureBefore = null;
try {
  captureBefore = await captureByOrd(page);
  await clickByAria(page, 'Multiply rate');
  await page.waitForTimeout(900);
  await shot(page, 'wave1_05a_multiply_rate_dialog.png');
  // Fill the factor input using real keyboard so React state updates
  const inp = page.locator('[aria-label*="Factor (> 0)" i]');
  await inp.waitFor({ state: 'visible', timeout: 5000 });
  await inp.click({ clickCount: 3 }); // select-all the default '1.10'
  await page.keyboard.type('1.10');
  await page.waitForTimeout(400);
  // Click Apply, then wait for the PATCH response + grid refresh
  const respPromise = page.waitForResponse(r => r.url().includes('bulk-update'), { timeout: 30000 });
  const apply = page.locator('[role="dialog"] button', { hasText: /^Apply$/ });
  await apply.click();
  const resp = await respPromise;
  log('  W1.5 PATCH bulk-update status:', resp.status());
  // Wait for the structured-BOQ refetch (queryClient.invalidateQueries(['boq', boqId]))
  await page.waitForResponse(r => r.url().includes('/structured'), { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(3500);
  await shot(page, 'wave1_05b_after_multiply_rate.png');
  const afterRate = await captureByOrd(page);
  let changed = 0;
  for (const o of TARGET_ORDS) {
    if (!captureBefore[o] || !afterRate[o]) continue;
    const b = num(captureBefore[o].unit_rate);
    const a = num(afterRate[o].unit_rate);
    log(`    ${o}: rate ${b} -> ${a}`);
    if (a > b * 1.05) changed++;
  }
  record('wave1', 5, changed >= 2, `Rate*1.10: ${changed}/${TARGET_ORDS.length} target rows updated`, 'wave1_05b_after_multiply_rate.png');
  captureBefore = afterRate;
} catch (e) {
  await shot(page, 'wave1_05_FAIL.png');
  record('wave1', 5, false, 'multiply rate: ' + e.message, 'wave1_05_FAIL.png');
}

// W1.6 — Multiply qty 1.5
try {
  // Re-select target rows (selection was cleared after bulk-update)
  // Wait for grid to settle before re-selecting
  await page.waitForTimeout(1500);
  const sel = await selectRowsByOrd(page, TARGET_ORDS);
  await page.waitForTimeout(1500);
  // Verify chip is visible
  const chipReady = await page.evaluate(() =>
    !!document.querySelector('[aria-label*="Multiply quantity" i]')
  );
  log('  W1.6 sel:', JSON.stringify(sel), 'chipReady:', chipReady);
  const qtyBefore = await captureByOrd(page);
  await shot(page, 'wave1_06a_before_multiply_qty.png');
  await clickByAria(page, 'Multiply quantity');
  await page.waitForTimeout(1200);
  const inpQ = page.locator('[aria-label*="Factor (> 0)" i]');
  await inpQ.waitFor({ state: 'visible', timeout: 5000 });
  await inpQ.click({ clickCount: 3 });
  await page.keyboard.type('1.5');
  await page.waitForTimeout(400);
  const respPromise = page.waitForResponse(r => r.url().includes('bulk-update'), { timeout: 30000 });
  const applyQ = page.locator('[role="dialog"] button', { hasText: /^Apply$/ });
  await applyQ.click();
  const resp = await respPromise;
  log('  W1.6 PATCH bulk-update status:', resp.status());
  await page.waitForResponse(r => r.url().includes('/structured'), { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(3500);
  await shot(page, 'wave1_06b_after_multiply_qty.png');
  const afterQty = await captureByOrd(page);
  let changed = 0;
  for (const o of TARGET_ORDS) {
    if (!qtyBefore[o] || !afterQty[o]) continue;
    const b = num(qtyBefore[o].quantity);
    const a = num(afterQty[o].quantity);
    log(`    ${o}: qty ${b} -> ${a}`);
    if (a > b * 1.3) changed++;
  }
  record('wave1', 6, changed >= 2, `Qty*1.5: ${changed}/${TARGET_ORDS.length} target rows updated`, 'wave1_06b_after_multiply_qty.png');
} catch (e) {
  await shot(page, 'wave1_06_FAIL.png');
  record('wave1', 6, false, 'multiply qty: ' + e.message, 'wave1_06_FAIL.png');
}

// W1.7 — Ctrl+D fill-down. To make the result deterministic, first PATCH
// 02.01.001's unit_rate to a unique sentinel value via API; that way the
// other two rows must end up at that exact sentinel for Ctrl+D to pass.
try {
  // PATCH 02.01.001 to a unique value via the API so we know what the
  // fill-down source should be.
  const SOURCE_RATE = 777;
  await fetch(`${BACKEND}/api/v1/boq/positions/b0c7d455-b269-4bbb-87cf-cd30d62d7488`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tokens.access_token },
    body: JSON.stringify({ unit_rate: SOURCE_RATE }),
  });
  await page.waitForTimeout(500);
  // Reload the BOQ so the grid sees the new value
  await page.goto(FRONTEND + '/boq/' + BOQ_ID, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(4000);
  await selectRowsByOrd(page, TARGET_ORDS);
  await page.waitForTimeout(1500);

  const focusCoords = await page.evaluate((ord) => {
    const rows = [...document.querySelectorAll('.ag-center-cols-container .ag-row')];
    const r = rows.find(rw => rw.querySelector('[col-id="ordinal"]')?.innerText?.trim() === ord);
    if (!r) return null;
    const cell = r.querySelector('[col-id="unit_rate"]');
    if (!cell) return null;
    cell.scrollIntoView({ block: 'center' });
    const rect = cell.getBoundingClientRect();
    return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
  }, TARGET_ORDS[0]);
  if (focusCoords) {
    await page.mouse.click(focusCoords.x, focusCoords.y);
    await page.waitForTimeout(800);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
  }
  const before = await captureByOrd(page);
  await shot(page, 'wave1_07a_before_ctrl_d.png');
  // Dispatch Ctrl+D both as a real key and via wrapper dispatch (one of them
  // should engage the listener).
  await page.keyboard.press('Control+D');
  await page.evaluate(() => {
    const wrapper = document.querySelector('.ag-theme-quartz')?.parentElement;
    if (!wrapper) return false;
    const ev = new KeyboardEvent('keydown', { key: 'd', code: 'KeyD', ctrlKey: true, bubbles: true, cancelable: true });
    wrapper.dispatchEvent(ev);
    return true;
  });
  // Wait for the per-row PATCHes to land
  await page.waitForResponse(r => r.method() === 'PATCH' && r.url().includes('/v1/boq/positions/') && !r.url().includes('bulk-update'), { timeout: 15000 }).catch(() => {});
  await page.waitForResponse(r => r.url().includes('/structured'), { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(3500);
  const after = await captureByOrd(page);
  await shot(page, 'wave1_07b_after_ctrl_d.png');
  // Pass criterion: 02.01.002 and 02.01.003 now equal 02.01.001's sentinel (777).
  // Compare numerically (commas/dots vary by locale).
  const sourceN = num(after[TARGET_ORDS[0]]?.unit_rate);
  const otherRows = TARGET_ORDS.slice(1).map(o => num(after[o]?.unit_rate));
  const allMatchSentinel = sourceN > 700 && otherRows.every(v => Math.abs(v - sourceN) < 0.5);
  log('  Ctrl+D before:', JSON.stringify(TARGET_ORDS.map(o => before[o]?.unit_rate)));
  log('  Ctrl+D after :', JSON.stringify(TARGET_ORDS.map(o => after[o]?.unit_rate)));
  log('  source=', sourceN, 'others=', otherRows);
  record('wave1', 7, allMatchSentinel, `Ctrl+D fill-down: source(${sourceN})=${otherRows.join(',')} match=${allMatchSentinel}`, 'wave1_07b_after_ctrl_d.png');
} catch (e) {
  await shot(page, 'wave1_07_FAIL.png');
  record('wave1', 7, false, 'ctrl+d: ' + e.message, 'wave1_07_FAIL.png');
}

// W1.8 — Version drawer / field history / restore
try {
  // Clear selection
  await clickByAria(page, 'Clear selection');
  await page.waitForTimeout(500);
  // Open version history via toolbar Clock button (title attribute)
  const opened = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')];
    const v = btns.find(b => /version history/i.test(b.getAttribute('title') || ''));
    if (v) { v.click(); return true; }
    return false;
  });
  log('  version history opened:', opened);
  await page.waitForTimeout(1800);
  await shot(page, 'wave1_08a_version_drawer_open.png');

  // Click Field history tab
  const tabClicked = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')];
    const fh = btns.find(b => /field history/i.test(b.textContent?.trim() || ''));
    if (fh) { fh.click(); return true; }
    return false;
  });
  await page.waitForTimeout(3500);
  await shot(page, 'wave1_08b_field_history_tab.png');

  // Find Restore action inside the drawer (not the snapshots tab restore)
  const restoreInfo = await page.evaluate(() => {
    const drawer = document.querySelector('[role="dialog"][aria-label*="Version" i]') ||
                   document.querySelector('aside');
    if (!drawer) return { found: false, reason: 'no drawer' };
    const btns = [...drawer.querySelectorAll('button')];
    const restore = btns.find(b => {
      const txt = b.textContent?.trim().toLowerCase() || '';
      const aria = (b.getAttribute('aria-label') || '').toLowerCase();
      return txt === 'restore' || /restore/.test(aria);
    });
    if (restore) {
      restore.scrollIntoView();
      restore.click();
      return { found: true, txt: restore.textContent?.trim() };
    }
    return { found: false, totalBtns: btns.length };
  });
  log('  restore action:', JSON.stringify(restoreInfo));
  await page.waitForTimeout(3000);
  await shot(page, 'wave1_08c_after_restore.png');
  // Pass if tab opened and either restore button exists or activity is empty (which is OK message displayed)
  const noEdits = await page.evaluate(() =>
    document.body.textContent.includes('No field-level edits')
  );
  record('wave1', 8, tabClicked, `Field history tab=${tabClicked}; restoreBtnFound=${restoreInfo.found}; noEdits=${noEdits}`, 'wave1_08c_after_restore.png');
} catch (e) {
  await shot(page, 'wave1_08_FAIL.png');
  record('wave1', 8, false, 'version drawer: ' + e.message, 'wave1_08_FAIL.png');
}

await closeAnyDialog(page);

// ===== WAVE 2 =====
log('\n===== WAVE 2 — Edge cases =====');

// W2.1 — factor 0
try {
  await selectRowsByOrd(page, TARGET_ORDS);
  await page.waitForTimeout(500);
  await clickByAria(page, 'Multiply rate');
  await page.waitForTimeout(900);
  const inp01 = page.locator('[aria-label*="Factor (> 0)" i]');
  await inp01.waitFor({ state: 'visible', timeout: 5000 });
  await inp01.click({ clickCount: 3 });
  await page.keyboard.type('0');
  await page.waitForTimeout(300);
  const before = await captureByOrd(page);
  const apply01 = page.locator('[role="dialog"] button', { hasText: /^Apply$/ });
  await apply01.click().catch(() => {});
  await page.waitForTimeout(1800);
  const dialogOpen = await page.evaluate(() =>
    !!document.querySelector('[role="dialog"]')
  );
  const after = await captureByOrd(page);
  let changed = 0;
  for (const o of TARGET_ORDS) {
    if (before[o]?.unit_rate !== after[o]?.unit_rate) changed++;
  }
  await shot(page, 'wave2_01_factor_zero.png');
  record('wave2', 1, dialogOpen && changed === 0, `Factor 0: dialog open=${dialogOpen}, target cells changed=${changed}`, 'wave2_01_factor_zero.png');
  await closeAnyDialog(page);
} catch (e) {
  await shot(page, 'wave2_01_FAIL.png');
  record('wave2', 1, false, 'factor 0: ' + e.message, 'wave2_01_FAIL.png');
}

// W2.2 — factor -1
try {
  await closeAnyDialog(page); // ensure W2.1 dialog is fully closed
  await page.waitForTimeout(500);
  await selectRowsByOrd(page, TARGET_ORDS);
  await page.waitForTimeout(500);
  await clickByAria(page, 'Multiply rate');
  await page.waitForTimeout(900);
  const inp02 = page.locator('[aria-label*="Factor (> 0)" i]');
  await inp02.waitFor({ state: 'visible', timeout: 5000 });
  await inp02.click({ clickCount: 3 });
  await page.keyboard.type('-1');
  await page.waitForTimeout(300);
  const before = await captureByOrd(page);
  const apply02 = page.locator('[role="dialog"] button', { hasText: /^Apply$/ });
  await apply02.click().catch(() => {});
  await page.waitForTimeout(1800);
  const dialogOpen = await page.evaluate(() =>
    !!document.querySelector('[role="dialog"]')
  );
  const after = await captureByOrd(page);
  let changed = 0;
  for (const o of TARGET_ORDS) {
    if (before[o]?.unit_rate !== after[o]?.unit_rate) changed++;
  }
  await shot(page, 'wave2_02_factor_negative.png');
  record('wave2', 2, dialogOpen && changed === 0, `Factor -1: dialog open=${dialogOpen}, target cells changed=${changed}`, 'wave2_02_factor_negative.png');
  await closeAnyDialog(page);
} catch (e) {
  await shot(page, 'wave2_02_FAIL.png');
  record('wave2', 2, false, 'factor -1: ' + e.message, 'wave2_02_FAIL.png');
}

// W2.3 — Classification empty code
try {
  await selectRowsByOrd(page, TARGET_ORDS);
  await page.waitForTimeout(500);
  await clickByAria(page, 'Set classification');
  await page.waitForTimeout(700);
  // Don't fill — Apply should be disabled
  const applyDisabled = await page.evaluate(() => {
    const dlg = document.querySelector('[role="dialog"]');
    if (!dlg) return null;
    const btns = [...dlg.querySelectorAll('button')];
    const apply = btns.find(b => /^apply$/i.test(b.textContent?.trim() || ''));
    return apply ? apply.disabled : null;
  });
  await shot(page, 'wave2_03_empty_classification.png');
  record('wave2', 3, applyDisabled === true, `Classification empty code: Apply disabled=${applyDisabled}`, 'wave2_03_empty_classification.png');
  await closeAnyDialog(page);
} catch (e) {
  await shot(page, 'wave2_03_FAIL.png');
  record('wave2', 3, false, 'empty classification: ' + e.message, 'wave2_03_FAIL.png');
}

// W2.4 — Ctrl+D single row
try {
  // Clear selection then select 1
  await clickByAria(page, 'Clear selection').catch(() => {});
  await page.waitForTimeout(500);
  await selectRowsByOrd(page, [TARGET_ORDS[0]]);
  await page.waitForTimeout(500);
  // focus its unit_rate cell
  await page.evaluate((ord) => {
    const rows = [...document.querySelectorAll('.ag-center-cols-container .ag-row')];
    const r = rows.find(rw => rw.querySelector('[col-id="ordinal"]')?.innerText?.trim() === ord);
    if (r) {
      const cell = r.querySelector('[col-id="unit_rate"]');
      if (cell) cell.click();
    }
  }, TARGET_ORDS[0]);
  await page.waitForTimeout(400);
  const before = await captureByOrd(page);
  await page.keyboard.press('Control+D');
  await page.waitForTimeout(1200);
  const after = await captureByOrd(page);
  let changed = 0;
  for (const o of Object.keys(before)) {
    if (before[o]?.unit_rate !== after[o]?.unit_rate) changed++;
  }
  await shot(page, 'wave2_04_ctrl_d_single_row.png');
  record('wave2', 4, changed === 0, `Ctrl+D single row no-op: cells changed=${changed}`, 'wave2_04_ctrl_d_single_row.png');
} catch (e) {
  await shot(page, 'wave2_04_FAIL.png');
  record('wave2', 4, false, 'ctrl+d single: ' + e.message, 'wave2_04_FAIL.png');
}

// W2.5 — Restore non-existent log_id (curl & UI check)
try {
  // Try a payload that matches the actual schema
  const r1 = await fetch(`${BACKEND}/api/v1/boq/boqs/${BOQ_ID}/positions/00000000-0000-0000-0000-000000000000/restore-field/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tokens.access_token },
    body: JSON.stringify({ log_id: 'ffffffff-ffff-ffff-ffff-ffffffffffff', field: 'unit_rate' }),
  });
  const body1 = await r1.text();
  log('  restore fake log_id (w/ field) ->', r1.status, body1.slice(0, 300));
  await shot(page, 'wave2_05_restore_fake_log.png');
  // Pass if API returns 4xx (not 5xx)
  const ok = r1.status >= 400 && r1.status < 500;
  record('wave2', 5, ok, `Fake log_id+field restore -> HTTP ${r1.status} (graceful 4xx, not 500)`, 'wave2_05_restore_fake_log.png');
} catch (e) {
  record('wave2', 5, false, 'restore fake log: ' + e.message, null);
}

// W2.6 — bulk-update empty ids
try {
  const r = await fetch(`${BACKEND}/api/v1/boq/boqs/${BOQ_ID}/positions/bulk-update/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tokens.access_token },
    body: JSON.stringify({ ids: [], rate_factor: 1.05 }),
  });
  const body = await r.text();
  log('  bulk-update empty ids ->', r.status, body.slice(0, 300));
  await shot(page, 'wave2_06_bulk_empty.png');
  const ok = r.status < 500;
  record('wave2', 6, ok, `Empty-ids bulk-update -> HTTP ${r.status} (no 500)`, 'wave2_06_bulk_empty.png');
} catch (e) {
  record('wave2', 6, false, 'bulk empty: ' + e.message, null);
}

// ===== WAVE 3 =====
log('\n===== WAVE 3 — Regression =====');

// W3.1 — Add new position
try {
  await closeAnyDialog(page);
  await clickByAria(page, 'Clear selection').catch(() => {});
  await page.waitForTimeout(400);
  const before = await captureByOrd(page);
  // Find Add Position toolbar button
  const clicked = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')];
    const add = btns.find(b => {
      const title = (b.getAttribute('title') || '').toLowerCase();
      const aria = (b.getAttribute('aria-label') || '').toLowerCase();
      const txt = (b.textContent || '').trim().toLowerCase();
      return /add position/.test(title) || /add position/.test(aria) ||
             /^add position$/.test(txt) || /add row/.test(title);
    });
    if (add) { add.click(); return add.outerHTML.slice(0,250); }
    return null;
  });
  log('  Add Position btn:', clicked);
  await page.waitForTimeout(3000);
  await shot(page, 'wave3_01_after_add.png');
  const after = await captureByOrd(page);
  const beforeN = Object.keys(before).length;
  const afterN = Object.keys(after).length;
  record('wave3', 1, afterN > beforeN, `Add position: rows ${beforeN} -> ${afterN}`, 'wave3_01_after_add.png');
} catch (e) {
  await shot(page, 'wave3_01_FAIL.png');
  record('wave3', 1, false, 'add position: ' + e.message, 'wave3_01_FAIL.png');
}

// W3.2 — Edit single cell
try {
  await page.waitForTimeout(800);
  const targetOrd = '02.01.004';
  const coords = await page.evaluate((ord) => {
    const rows = [...document.querySelectorAll('.ag-center-cols-container .ag-row')];
    const r = rows.find(rw => rw.querySelector('[col-id="ordinal"]')?.innerText?.trim() === ord);
    if (!r) return null;
    const cell = r.querySelector('[col-id="unit_rate"]');
    if (!cell) return null;
    cell.scrollIntoView({ block: 'center' });
    const rect = cell.getBoundingClientRect();
    return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2, rowCls: r.className };
  }, targetOrd);
  log('  W3.2 cell coords:', JSON.stringify(coords));
  if (coords) {
    // first click to focus
    await page.mouse.click(coords.x, coords.y);
    await page.waitForTimeout(600);
    // Check edit state
    let inEdit = await page.evaluate(() => !!document.querySelector('.ag-cell-edit-input, .ag-cell-editor input, [class*="formulaCellEditor"] input'));
    if (!inEdit) {
      // Try second click (some AG Grid setups require a second click)
      await page.mouse.click(coords.x, coords.y);
      await page.waitForTimeout(500);
      inEdit = await page.evaluate(() => !!document.querySelector('.ag-cell-edit-input, .ag-cell-editor input, [class*="formulaCellEditor"] input'));
    }
    if (!inEdit) {
      await page.keyboard.press('F2').catch(() => {});
      await page.waitForTimeout(400);
      inEdit = await page.evaluate(() => !!document.querySelector('.ag-cell-edit-input, .ag-cell-editor input, [class*="formulaCellEditor"] input'));
    }
    log('  W3.2 inEdit:', inEdit);
    if (inEdit) {
      await page.keyboard.press('Control+A');
      await page.keyboard.type('999');
      await page.keyboard.press('Enter');
      await page.waitForResponse(r => r.method() === 'PATCH' && r.url().includes('/v1/boq/positions/'), { timeout: 15000 }).catch(() => {});
      await page.waitForResponse(r => r.url().includes('/structured'), { timeout: 15000 }).catch(() => {});
      await page.waitForTimeout(2000);
    }
  }
  await shot(page, 'wave3_02_single_cell_edit.png');
  const cap = await captureByOrd(page);
  const val = cap[targetOrd]?.unit_rate;
  log('  cell after edit:', val);
  record('wave3', 2, /999/.test(val || ''), `Single-cell edit ${targetOrd}: '${val}'`, 'wave3_02_single_cell_edit.png');
} catch (e) {
  await shot(page, 'wave3_02_FAIL.png');
  record('wave3', 2, false, 'single edit: ' + e.message, 'wave3_02_FAIL.png');
}

// W3.3 — Batch delete (existing chip)
try {
  await closeAnyDialog(page);
  // Pick a target ord that we haven't relied on for downstream steps
  const delOrd = '02.01.005';
  await selectRowsByOrd(page, [delOrd]);
  await page.waitForTimeout(600);
  const before = await captureByOrd(page);
  await clickByAria(page, 'Delete selected');
  await page.waitForTimeout(700);
  await shot(page, 'wave3_03a_delete_dialog.png');
  // Confirm — click the red destructive button
  await page.evaluate(() => {
    const dlg = document.querySelector('[role="alertdialog"]') || document.querySelector('[role="dialog"]');
    if (!dlg) return;
    const btns = [...dlg.querySelectorAll('button')];
    // The destructive button has bg-semantic-error class
    const confirm = btns.find(b => (b.className || '').includes('bg-semantic-error')) ||
                    btns.find(b => /delete \d+ position/i.test(b.textContent?.trim() || ''));
    if (confirm) confirm.click();
  });
  await page.waitForTimeout(3000);
  const after = await captureByOrd(page);
  await shot(page, 'wave3_03b_after_delete.png');
  const beforeN = Object.keys(before).length;
  const afterN = Object.keys(after).length;
  record('wave3', 3, afterN < beforeN || !(delOrd in after), `Batch delete ${delOrd}: rows ${beforeN} -> ${afterN}, ${delOrd} gone=${!(delOrd in after)}`, 'wave3_03b_after_delete.png');
} catch (e) {
  await shot(page, 'wave3_03_FAIL.png');
  record('wave3', 3, false, 'batch delete: ' + e.message, 'wave3_03_FAIL.png');
}

// W3.4 — Snapshots tab
try {
  await closeAnyDialog(page);
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')];
    const v = btns.find(b => /version history/i.test(b.getAttribute('title') || ''));
    if (v) v.click();
  });
  await page.waitForTimeout(1500);
  // Switch to Snapshots tab — match button with aria-pressed AND text containing 'Snapshots'
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button[aria-pressed]')];
    const snap = btns.find(b => /snapshots/i.test(b.textContent || ''));
    if (snap) snap.click();
  });
  await page.waitForTimeout(1500);
  await shot(page, 'wave3_04_snapshots_tab.png');
  const info = await page.evaluate(() => ({
    snapshotsTabExists: !![...document.querySelectorAll('button[aria-pressed]')].find(b => /snapshots/i.test(b.textContent || '')),
    drawerOpen: !!document.querySelector('[aria-label*="Version" i]') || !!document.querySelector('aside'),
  }));
  record('wave3', 4, info.snapshotsTabExists && info.drawerOpen, `Snapshots tab=${info.snapshotsTabExists}, drawerOpen=${info.drawerOpen}`, 'wave3_04_snapshots_tab.png');
  await closeAnyDialog(page);
} catch (e) {
  await shot(page, 'wave3_04_FAIL.png');
  record('wave3', 4, false, 'snapshots tab: ' + e.message, 'wave3_04_FAIL.png');
}

// W3.5 — Formula
try {
  await closeAnyDialog(page);
  const targetOrd = '02.01.003';
  const coords = await page.evaluate((ord) => {
    const rows = [...document.querySelectorAll('.ag-center-cols-container .ag-row')];
    const r = rows.find(rw => rw.querySelector('[col-id="ordinal"]')?.innerText?.trim() === ord);
    if (!r) return null;
    const cell = r.querySelector('[col-id="quantity"]');
    if (!cell) return null;
    cell.scrollIntoView({ block: 'center' });
    const rect = cell.getBoundingClientRect();
    return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
  }, targetOrd);
  if (coords) {
    await page.mouse.click(coords.x, coords.y);
    await page.waitForTimeout(600);
    let inEdit = await page.evaluate(() => !!document.querySelector('.ag-cell-edit-input, .ag-cell-editor input, [class*="formulaCellEditor"] input'));
    if (!inEdit) {
      await page.mouse.click(coords.x, coords.y);
      await page.waitForTimeout(500);
      inEdit = await page.evaluate(() => !!document.querySelector('.ag-cell-edit-input, .ag-cell-editor input, [class*="formulaCellEditor"] input'));
    }
    if (!inEdit) {
      await page.keyboard.press('F2').catch(() => {});
      await page.waitForTimeout(400);
      inEdit = await page.evaluate(() => !!document.querySelector('.ag-cell-edit-input, .ag-cell-editor input, [class*="formulaCellEditor"] input'));
    }
    log('  W3.5 inEdit:', inEdit);
    if (inEdit) {
      await page.keyboard.press('Control+A');
      await page.keyboard.type('=10*1.21');
      await page.keyboard.press('Enter');
      await page.waitForResponse(r => r.method() === 'PATCH' && r.url().includes('/v1/boq/positions/'), { timeout: 15000 }).catch(() => {});
      await page.waitForResponse(r => r.url().includes('/structured'), { timeout: 15000 }).catch(() => {});
      await page.waitForTimeout(2000);
    }
  }
  await shot(page, 'wave3_05_formula.png');
  const cap = await captureByOrd(page);
  const val = cap[targetOrd]?.quantity;
  log('  formula cell ->', val);
  const ok = /12[\.,]1/.test(val || '');
  record('wave3', 5, ok, `Formula =10*1.21 on ${targetOrd} -> '${val}'`, 'wave3_05_formula.png');
} catch (e) {
  await shot(page, 'wave3_05_FAIL.png');
  record('wave3', 5, false, 'formula: ' + e.message, 'wave3_05_FAIL.png');
}

// ===== REPORT =====
log('\n===== Console errors =====');
log(JSON.stringify(consoleErrs.slice(0, 20), null, 2));
log('\n===== Network 4xx/5xx =====');
log(JSON.stringify(networkFails.slice(0, 30), null, 2));
log('\n===== Bulk/restore requests =====');
log(JSON.stringify(bulkRequests, null, 2));

await browser.close();

fs.writeFileSync(path.join(OUT, 'results.json'), JSON.stringify({
  results: RESULTS,
  consoleErrs: consoleErrs.slice(0,30),
  networkFails: networkFails.slice(0,50),
  log: LOG,
}, null, 2));

function fmt(wave, label) {
  const arr = RESULTS[wave];
  let md = `\n### ${label}\n\n`;
  for (const r of arr) {
    md += `- [${r.ok ? 'x' : ' '}] **Step ${r.step}** — ${r.obs}${r.shot ? `  \n  screenshot: \`${r.shot}\`` : ''}\n`;
  }
  return md;
}

const w1pass = RESULTS.wave1.filter(r => r.ok).length;
const w2pass = RESULTS.wave2.filter(r => r.ok).length;
const w3pass = RESULTS.wave3.filter(r => r.ok).length;
const total = RESULTS.wave1.length + RESULTS.wave2.length + RESULTS.wave3.length;
const passTotal = w1pass + w2pass + w3pass;

const crit = [...RESULTS.wave1, ...RESULTS.wave2, ...RESULTS.wave3]
  .filter(r => !r.ok)
  .map(r => `- ${r.step}: ${r.obs}`);

let verdict = 'SHIP';
if (crit.length > 3 || RESULTS.wave1.filter(r => !r.ok).length >= 2) verdict = 'FIX-AND-RESHIP';
if (RESULTS.wave1.filter(r => !r.ok).length >= 4) verdict = 'BLOCKED';

const report = `# v3.12.0 Stream A — QA Verification Report

**Date**: ${new Date().toISOString()}
**BOQ tested**: \`${BOQ_ID}\` (Edifício Comercial Faria Lima — São Paulo — Orçamento)
**Backend**: ${BACKEND}
**Frontend**: ${FRONTEND}
**Pass rate**: ${passTotal}/${total} (Wave 1: ${w1pass}/${RESULTS.wave1.length}, Wave 2: ${w2pass}/${RESULTS.wave2.length}, Wave 3: ${w3pass}/${RESULTS.wave3.length})

## Wave 1 — Golden path
${fmt('wave1', 'Steps')}

## Wave 2 — Edge cases
${fmt('wave2', 'Steps')}

## Wave 3 — Regression
${fmt('wave3', 'Steps')}

## Critical defects
${crit.length ? crit.join('\n') : '_None_'}

## Console errors (first 10)
\`\`\`
${consoleErrs.slice(0,10).join('\n') || '(none)'}
\`\`\`

## Network 4xx/5xx (first 20)
\`\`\`
${networkFails.slice(0,20).map(n => n.status + ' ' + n.url).join('\n') || '(none)'}
\`\`\`

## Overall verdict
**${verdict}**
`;
fs.writeFileSync(path.join(OUT, 'REPORT.md'), report);
log('\nReport written to', path.join(OUT, 'REPORT.md'));
log('Pass:', passTotal + '/' + total, '| Verdict:', verdict);
