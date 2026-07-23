// Standalone Playwright walkthrough — no playwright.config.ts, no webServer.
// Hits the live dev stack on http://localhost:5180.
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

// Target the user's actual running stack: openestimate CLI on 8080 serves
// both the SPA and the API. That way we test against the same DB the
// user sees and don't have to worry about a fresh empty test backend.
const BASE = 'http://127.0.0.1:8090';
const API = 'http://127.0.0.1:8090/api/v1';
const SHOTS = path.resolve('qa-shots/file-deeplink');
fs.mkdirSync(SHOTS, { recursive: true });

// Just one known-good test account — multiple attempts trigger the
// backend's auth rate limit (~5/min) and lock us out.
const CANDIDATES = [
  { email: 'v19-e2e@openestimate.com', password: 'OpenEstimate2024!' },
];

async function tryLogin(email, password) {
  const r = await fetch(`${API}/users/auth/login/`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  return r.ok ? (await r.json()).access_token : null;
}

async function listProjects(token) {
  const r = await fetch(`${API}/projects/`, {
    headers: { authorization: `Bearer ${token}` },
  });
  if (!r.ok) return [];
  const j = await r.json();
  return Array.isArray(j) ? j : (j.items ?? j.projects ?? []);
}

async function createProject(token, name) {
  const r = await fetch(`${API}/projects/`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
    body: JSON.stringify({ name, code: 'QA-FILES', description: 'walkthrough' }),
  });
  if (!r.ok) {
    console.log('createProject failed:', r.status, await r.text());
    return null;
  }
  return await r.json();
}

async function uploadDocument(token, projectId, filename, contents) {
  const fd = new FormData();
  const blob = new Blob([contents], { type: 'application/pdf' });
  fd.append('file', blob, filename);
  fd.append('project_id', projectId);
  fd.append('category', 'general');
  const r = await fetch(`${API}/documents/`, {
    method: 'POST',
    headers: { authorization: `Bearer ${token}` },
    body: fd,
  });
  if (!r.ok) {
    console.log('uploadDocument failed:', r.status, await r.text());
    return null;
  }
  return await r.json();
}

async function ensureUser() {
  for (const c of CANDIDATES) {
    const token = await tryLogin(c.email, c.password);
    if (!token) continue;
    let projects = await listProjects(token);
    console.log(`tried ${c.email}: ${projects.length} project(s)`);
    if (!projects.length) {
      const p = await createProject(token, 'QA Walkthrough Project');
      if (p) {
        console.log('created project:', p.id);
        // Seed a tiny PDF so kind=document has at least one file.
        const minimalPdf =
          '%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n' +
          '2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n' +
          '3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n' +
          'xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000090 00000 n\n' +
          'trailer<</Size 4/Root 1 0 R>>\nstartxref\n140\n%%EOF\n';
        const doc = await uploadDocument(token, p.id, 'sample-spec.pdf', minimalPdf);
        if (doc) console.log('uploaded doc:', doc.id);
      }
      projects = await listProjects(token);
    }
    if (projects.length) return { token, projects, email: c.email };
  }
  // Fall back: register and use empty account.
  const u = CANDIDATES[CANDIDATES.length - 1];
  await fetch(`${API}/users/auth/register/`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ ...u, full_name: 'QA' }),
  });
  const token = await tryLogin(u.email, u.password);
  if (!token) throw new Error('login failed after register');
  return { token, projects: [], email: u.email };
}

async function shot(page, name) {
  const f = path.join(SHOTS, `${name}.png`);
  await page.screenshot({ path: f, fullPage: true });
  console.log(`  → ${f}`);
}

(async () => {
  const { token, projects, email } = await ensureUser();
  console.log(`logged in as ${email}, ${projects.length} project(s)`);
  const projectId = projects[0]?.id ?? null;
  console.log('using projectId:', projectId);

  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const projectName = projects[0]?.name ?? '';
  await ctx.addInitScript(({ t, pid, pname }) => {
    localStorage.setItem('oe_access_token', t);
    localStorage.setItem('oe_refresh_token', t);
    sessionStorage.setItem('oe_skip_onboarding_redirect', '1');
    if (pid) {
      // Real key from useProjectContextStore — JSON-encoded ProjectContext.
      localStorage.setItem('oe_active_project', JSON.stringify({ id: pid, name: pname, boqId: null }));
    }
    localStorage.setItem('oe_onboarding_completed', '1');
    localStorage.setItem('oe_tour_dismissed', '1');
  }, { t: token, pid: projectId, pname: projectName });
  const page = await ctx.newPage();
  page.on('console', (m) => {
    if (m.type() === 'error') console.log('[browser-error]', m.text().slice(0, 200));
  });

  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(3500);
  await shot(page, 'dashboard');
  // Sidebar zoom: capture the bottom 380px so we see Community card +
  // version footer in detail.
  const sidebarFooter = page.locator('aside').first();
  if (await sidebarFooter.count()) {
    await sidebarFooter.screenshot({
      path: 'qa-shots/file-deeplink/dashboard-sidebar.png',
      animations: 'disabled',
    });
    console.log('  → qa-shots/file-deeplink/dashboard-sidebar.png');
  }
  console.log('dashboard url:', page.url());

  await page.goto(`${BASE}/files`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await shot(page, '00-files-landing');
  console.log('url:', page.url());

  for (const kind of ['document', 'photo', 'bim_model', 'dwg_drawing']) {
    console.log(`\n=== kind=${kind} ===`);
    await page.goto(`${BASE}/files?kind=${kind}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    await shot(page, `01-${kind}-list`);

    // The file grid renders each tile as a <button> wrapped in a div.
    // Find any button that lives inside the main grid (has aspect-[4/3]
    // child div) — that's a file card. List view is a <tr>.
    const card = page.locator('button:has(.aspect-\\[4\\/3\\])').first();
    let clicked = false;
    if (await card.count()) {
      console.log(`  clicking grid card`);
      await card.click().catch(() => {});
      clicked = true;
    } else {
      const row = page.locator('tbody tr').first();
      if (await row.count()) {
        console.log(`  clicking list row`);
        await row.click().catch(() => {});
        clicked = true;
      }
    }
    if (!clicked) {
      console.log(`  no file row found`);
      continue;
    }
    await page.waitForTimeout(800);
    await shot(page, `02-${kind}-preview`);

    // The primary CTA lives inside the right-hand File details / preview
    // pane. Scope to that pane so the sidebar's "Documents" link doesn't
    // win the .filter() race. The pane has a heading text "File details".
    const pane = page.locator('aside, div').filter({ hasText: 'File details' }).first();
    const cta = pane.locator('button, a').filter({ hasText: /^Open in / }).first();
    if (!(await cta.count())) {
      console.log(`  no "Open in" CTA visible`);
      continue;
    }
    const ctaText = await cta.textContent();
    console.log(`  cta="${ctaText?.trim()}"`);
    await cta.click().catch(() => {});
    await page.waitForLoadState('networkidle').catch(() => {});
    await page.waitForTimeout(1500);
    console.log('  arrived at:', page.url());
    await shot(page, `03-${kind}-destination`);
  }

  await browser.close();
  console.log('\ndone — see', SHOTS);
})().catch((e) => {
  console.error('FAIL:', e);
  process.exit(1);
});
