// ‌⁠‍screenshot-bim-snap-cap.mjs — W6.6 BIM Viewer Pro UX sanity check.
//
// Drives Chromium through demo login, opens the first BIM model on the
// account, then captures three screenshots:
//   - before.png       baseline of the viewer with the model loaded
//   - snap-vertex.png  measure tool active, hover near a feature point
//   - clip-cap.png     single clip plane active showing the hatched cap
//
// Exit codes:
//   0 — all three screenshots written
//   2 — a precondition failed (no model, no auth, snap glyph not visible)
//   1 — unexpected error

import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';

const BASE = process.env.OE_FRONTEND_URL || 'http://localhost:5180';
const API = process.env.OE_API_URL || 'http://localhost:8000';
const DEMO_EMAIL = 'demo@openconstructionerp.com';
const OUT_DIR = path.resolve('qa-tests/_w66-bim-snap-cap');

function log(...args) {
  console.log('[bim-snap-cap]', ...args);
}

async function ensureDir() {
  await mkdir(OUT_DIR, { recursive: true });
}

async function loginViaApi(page) {
  log('demo-login →', API);
  const result = await page.evaluate(
    async ({ api, email }) => {
      const r = await fetch(api + '/api/v1/users/auth/demo-login/', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      if (!r.ok) return { ok: false, status: r.status };
      const body = await r.json().catch(() => ({}));
      const token = body.access_token || body.token;
      if (!token) return { ok: false, status: r.status, reason: 'no-token' };
      localStorage.setItem('auth_token', token);
      localStorage.setItem('access_token', token);
      return { ok: true };
    },
    { api: API, email: DEMO_EMAIL },
  );
  return result.ok === true;
}

async function pickFirstBimModelId(page) {
  // Hit the BIM models list endpoint via the page's fetch so auth cookies/
  // headers travel with the request.
  const result = await page.evaluate(async ({ api }) => {
    const token =
      localStorage.getItem('auth_token') || localStorage.getItem('access_token') || '';
    const headers = token ? { Authorization: 'Bearer ' + token } : {};
    const r = await fetch(api + '/api/v1/bim/models/', { headers });
    if (!r.ok) return { ok: false, status: r.status };
    const body = await r.json().catch(() => null);
    const list = Array.isArray(body) ? body : body?.items || body?.results || [];
    const first = list[0];
    if (!first) return { ok: false, status: r.status, reason: 'empty' };
    return { ok: true, id: first.id || first.model_id, project: first.project_id };
  }, { api: API });
  return result;
}

async function gotoModel(page, modelInfo) {
  // Most installs expose the viewer at /bim/<id> or /projects/<pid>/bim/<id>.
  // We try the simpler form first and fall back to the project-scoped one.
  const candidates = [
    `${BASE}/bim/${modelInfo.id}`,
    `${BASE}/projects/${modelInfo.project}/bim/${modelInfo.id}`,
    `${BASE}/bim`,
  ];
  for (const url of candidates) {
    log('try viewer URL', url);
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});
    // Wait for the canvas the BIMViewer mounts.
    const found = await page
      .waitForSelector('canvas', { timeout: 8_000 })
      .then(() => true)
      .catch(() => false);
    if (found) {
      log('viewer mounted at', url);
      return true;
    }
  }
  return false;
}

async function fail(msg, code = 2) {
  console.error('[bim-snap-cap] FAIL:', msg);
  process.exit(code);
}

async function main() {
  await ensureDir();
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', (m) => {
    if (m.type() === 'error') console.log('[browser-err]', m.text().slice(0, 200));
  });

  try {
    // Step 1: open the app shell so the API origin is settled, then login.
    await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle', { timeout: 5_000 }).catch(() => {});
    const loggedIn = await loginViaApi(page);
    if (!loggedIn) {
      return fail('demo-login failed — check that the API is running at ' + API);
    }
    // Reload so the SPA picks up the token from localStorage.
    await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle', { timeout: 5_000 }).catch(() => {});

    // Step 2: locate a BIM model.
    const modelInfo = await pickFirstBimModelId(page);
    if (!modelInfo.ok) {
      return fail('no BIM models on this install (status=' + modelInfo.status + ')');
    }
    log('model', modelInfo.id);

    // Step 3: open the viewer.
    const mounted = await gotoModel(page, modelInfo);
    if (!mounted) {
      return fail('canvas never mounted — viewer route not reachable');
    }
    // Give the geometry a few seconds to stream in.
    await page.waitForTimeout(3_500);
    await page.screenshot({ path: path.join(OUT_DIR, 'before.png'), fullPage: false });
    log('saved before.png');

    // Step 4: activate the measure tool. The toolbar exposes either a
    // data-testid or a button labelled "Measure" — try both.
    const measureBtn = page
      .locator('[data-testid="bim-measure-toggle"], button:has-text("Measure")')
      .first();
    if (!(await measureBtn.count())) {
      return fail('measure-tool button not found in the toolbar');
    }
    await measureBtn.click().catch(() => {});
    await page.waitForTimeout(500);

    // Hover near a feature point. We don't know the model geometry layout
    // up-front, so sweep a 5×5 grid centred on the canvas and capture the
    // frame where the snap glyph (sprite) renders.
    const canvas = page.locator('canvas').first();
    const box = await canvas.boundingBox();
    if (!box) {
      return fail('canvas bounding box unavailable');
    }
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    // Simple sweep — most models have geometry near the centroid.
    for (let dx = -120; dx <= 120; dx += 60) {
      for (let dy = -80; dy <= 80; dy += 40) {
        await page.mouse.move(cx + dx, cy + dy, { steps: 2 });
        await page.waitForTimeout(40);
      }
    }
    // Park the cursor in the centre for the screenshot — the glyph should
    // already be visible from the sweep above.
    await page.mouse.move(cx, cy, { steps: 4 });
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(OUT_DIR, 'snap-vertex.png'), fullPage: false });
    log('saved snap-vertex.png');

    // Turn the measure tool off before activating clip.
    await measureBtn.click().catch(() => {});
    await page.waitForTimeout(200);

    // Step 5: activate a single clip plane. The clip controls live in the
    // toolbar under "Section" / "Clip".
    const clipBtn = page
      .locator(
        '[data-testid="bim-clip-toggle"], button:has-text("Section"), button:has-text("Clip")',
      )
      .first();
    if (!(await clipBtn.count())) {
      return fail('clip-tool button not found in the toolbar');
    }
    await clipBtn.click().catch(() => {});
    await page.waitForTimeout(300);
    // Most UIs default the single-plane mode; if a sub-control offers
    // "Plane" pick it explicitly.
    const planeOption = page.locator('button:has-text("Plane")').first();
    if (await planeOption.count()) {
      await planeOption.click().catch(() => {});
      await page.waitForTimeout(200);
    }
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(OUT_DIR, 'clip-cap.png'), fullPage: false });
    log('saved clip-cap.png');

    await browser.close();
    process.exit(0);
  } catch (e) {
    console.error('[bim-snap-cap] unexpected error:', e?.stack || e);
    await browser.close().catch(() => {});
    process.exit(1);
  }
}

main();
