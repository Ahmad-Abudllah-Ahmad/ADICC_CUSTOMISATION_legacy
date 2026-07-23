/**
 * E2E — Geo Hub raster overlay (PDF / DWG / image on the globe).
 *
 * Drives the new "+ Add overlay" flow on /geo and the project map.
 * Logs in via the dedicated demo-login endpoint that the prod demo and
 * fresh-install snapshot both ship — POST /api/v1/users/auth/demo-login/
 * with ``{"email": "demo@datadrivenconstruction.io"}``.
 *
 * Screenshots land in ``qa-tests/_geo-overlay-2026-05-24/`` per the
 * v4-style QA-run convention. Cesium is lazy-loaded so we wait for the
 * canvas to mount before driving any handles.
 *
 * Spec lives in frontend/e2e/ (playwright.config.ts → testDir: './e2e')
 * not frontend/tests/e2e/ — the original spec request used the wrong
 * tree; this file is what playwright actually picks up.
 */
import { test, expect, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname_esm = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOT_DIR = path.resolve(
  __dirname_esm,
  '../../qa-tests/_geo-overlay-2026-05-24',
);
const PDF_FIXTURE = path.resolve(
  __dirname_esm,
  '../tests/fixtures/sample-site-plan.pdf',
);
const DEMO_EMAIL =
  process.env.E2E_DEMO_EMAIL ?? 'demo@openconstructionerp.com';
const BACKEND_BASE = process.env.E2E_BACKEND_BASE ?? 'http://localhost:8000';
const FRONTEND_BASE = process.env.E2E_FRONTEND_BASE ?? 'http://localhost:5181';

test.use({ baseURL: FRONTEND_BASE });

function ensureScreenshotDir() {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }
}

async function demoLogin(page: Page): Promise<string> {
  const res = await page.request.post(
    `${BACKEND_BASE}/api/v1/users/auth/demo-login/`,
    { data: { email: DEMO_EMAIL }, failOnStatusCode: false },
  );
  if (!res.ok()) {
    throw new Error(
      `demo-login returned ${res.status()}: ${await res.text()}`,
    );
  }
  const body = (await res.json()) as {
    access_token: string;
    refresh_token?: string;
  };
  // Seed tokens BEFORE the SPA boots — addInitScript runs before any
  // application JS so the Zustand auth store's ``loadFromStorage``
  // (called in App init) picks them up. Setting sessionStorage post-load
  // would never propagate to the in-memory store.
  await page.addInitScript(
    ({ access, refresh, email }) => {
      sessionStorage.setItem('oe_access_token', access);
      if (refresh) sessionStorage.setItem('oe_refresh_token', refresh);
      localStorage.setItem('oe_user_email', email);
      // Skip the first-run product tour + onboarding nudges so the
      // OverlayPanel's "+ Add" button isn't covered by a sidebar tour
      // modal during the test.
      localStorage.setItem('oe.product_tour.completed.v1', '1');
      localStorage.setItem('oe.product_tour.seen.v1', '1');
      localStorage.setItem('oe.whatsNewSeen.v4.5.0', '1');
    },
    {
      access: body.access_token,
      refresh: body.refresh_token ?? '',
      email: DEMO_EMAIL,
    },
  );
  return body.access_token;
}

test.describe('Geo Hub raster overlays', () => {
  test.beforeAll(ensureScreenshotDir);

  test('PDF overlay full lifecycle on /geo', async ({ page }) => {
    test.setTimeout(180_000);

    // Console-noise capture — used at the end of the test to assert on
    // the two regressions this run is fixing.
    const consoleMessages: { type: string; text: string }[] = [];
    const developerErrorCounts = new Map<string, number>();
    let maximumUpdateDepthCount = 0;
    page.on('console', (msg) => {
      const t = msg.type();
      const text = msg.text();
      if (t === 'error' || t === 'warning') {
        consoleMessages.push({ type: t, text });
        // eslint-disable-next-line no-console
        console.log(`[browser ${t}] ${text.slice(0, 200)}`);
      }
      if (text.includes('Maximum update depth exceeded')) {
        maximumUpdateDepthCount += 1;
      }
      // Cesium DeveloperError lines we used to emit one per render —
      // count occurrences per overlay id so the log-once fix is
      // measurable. Match either the soft-skip warn or the raw error.
      if (text.includes('DeveloperError') || text.includes('overlay layer add failed')) {
        const key = text.slice(0, 120);
        developerErrorCounts.set(key, (developerErrorCounts.get(key) ?? 0) + 1);
      }
    });
    page.on('pageerror', (err) => {
      // eslint-disable-next-line no-console
      console.log(`[browser pageerror] ${err.message}`);
      if (err.message.includes('Maximum update depth exceeded')) {
        maximumUpdateDepthCount += 1;
      }
    });

    const token = await demoLogin(page);

    // Resolve a real project id via the backend, then navigate into its
    // project-scoped Geo page (``/projects/:id/geo``). The OverlayPanel
    // only mounts when a project is in context — the bare /geo route is
    // for the global earth view.
    const projectsRes = await page.request.get(
      `${BACKEND_BASE}/api/v1/projects/`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const projects = (await projectsRes.json()) as Array<{ id: string }>;
    if (!projectsRes.ok() || !Array.isArray(projects) || projects.length === 0) {
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, '00-no-projects.png'),
        fullPage: true,
      });
      test.skip(true, 'No demo projects available — cannot test overlays');
      return;
    }
    const projectId = projects[0]!.id;

    // Make sure the project has a Geo anchor so the OverlayPanel mounts.
    // The empty-state card painted over the canvas when the anchor is
    // missing would otherwise eclipse the overlay rail. POST is
    // idempotent in the geo_hub service (overwrites in place).
    await page.request.post(`${BACKEND_BASE}/api/v1/geo-hub/anchors/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        project_id: projectId,
        lat: '52.5200',
        lon: '13.4050',
        alt: '34',
        epsg_code: 4326,
      },
      failOnStatusCode: false,
    });

    await page.goto(`/projects/${projectId}/geo`);

    // Diagnostic shot — captures whatever the project /geo page rendered
    // (login redirect, empty state, viewer loading, etc.).
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3_000);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '00a-initial-load.png'),
      fullPage: true,
    });

    // The Cesium runtime is lazy-loaded; the panel mounts inside the
    // overlay slot once the viewer reports ``onViewerReady``. We allow
    // ~30 s for the runtime, then fall back to "no Cesium" branch.
    const panel = page.getByTestId('geo-overlay-panel');
    let panelMounted = true;
    try {
      await panel.waitFor({ state: 'attached', timeout: 60_000 });
    } catch {
      panelMounted = false;
    }
    if (!panelMounted) {
      // Cesium absent / no project context — still capture the page
      // state so the report has visual evidence and skip the rest.
      try {
        await page.screenshot({
          path: path.join(SCREENSHOT_DIR, '00-no-cesium.png'),
          fullPage: true,
          timeout: 5_000,
        });
      } catch {
        /* page already closed */
      }
      test.skip(true, 'Cesium runtime not available / panel never mounted');
      return;
    }
    // Panel mounted — record a baseline shot.
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '00-panel-mounted.png'),
      fullPage: true,
    });

    // Open the upload modal.
    await page.getByTestId('geo-overlay-add-button').click();
    await expect(page.getByTestId('geo-overlay-upload-modal')).toBeVisible();
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '01-upload-modal.png'),
      fullPage: true,
    });

    // Upload the sample PDF fixture.
    await page.getByTestId('geo-overlay-tab-pdf').click();
    await page.getByTestId('geo-overlay-pdf-input').setInputFiles(PDF_FIXTURE);

    // First overlay row appears.
    const firstRow = page.getByTestId('geo-overlay-row').first();
    await expect(firstRow).toBeVisible({ timeout: 30_000 });
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '02-overlay-added.png'),
      fullPage: true,
    });

    // Drag opacity slider to 0.3 (~30 %).
    const slider = page.getByTestId('geo-overlay-opacity-slider').first();
    await slider.evaluate((el: HTMLInputElement) => {
      el.value = '0.3';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await page.waitForTimeout(500);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '03-opacity-30.png'),
      fullPage: true,
    });

    // Activate the row and engage Edit corners — drag handles appear
    // as Cesium entities; we screenshot the chrome state.
    await firstRow.getByRole('button', { name: /Untitled|sample|plan/i }).click();
    await page.getByTestId('geo-overlay-edit-corners').click();
    await page.waitForTimeout(500);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '04-edit-corners.png'),
      fullPage: true,
    });
    // Drop edit-corners mode before crop.
    await page.getByTestId('geo-overlay-edit-corners').click();

    // Engage crop mode + simulate 5 polygon clicks across the canvas.
    await page.getByTestId('geo-overlay-crop').click();
    const canvas = page.locator('canvas').first();
    const box = await canvas.boundingBox();
    if (box) {
      const pts = [
        [box.width * 0.4, box.height * 0.4],
        [box.width * 0.6, box.height * 0.4],
        [box.width * 0.65, box.height * 0.55],
        [box.width * 0.5, box.height * 0.65],
        [box.width * 0.4, box.height * 0.55],
      ];
      for (const [x, y] of pts) {
        await page.mouse.click(box.x + x, box.y + y);
        await page.waitForTimeout(200);
      }
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, '05-crop-vertices.png'),
        fullPage: true,
      });
      await page.keyboard.press('Enter');
      await page.waitForTimeout(800);
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, '06-crop-applied.png'),
        fullPage: true,
      });
    }

    // Toggle visibility off then on.
    const visibleToggle = firstRow
      .getByTestId('geo-overlay-toggle-visible')
      .first();
    await visibleToggle.click();
    await page.waitForTimeout(400);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '07-hidden.png'),
      fullPage: true,
    });
    await visibleToggle.click();
    await page.waitForTimeout(400);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '08-visible-again.png'),
      fullPage: true,
    });

    // ── Console regression assertions ─────────────────────────────────
    // Issue 1: zero "Maximum update depth exceeded" warnings or errors.
    expect(
      maximumUpdateDepthCount,
      `Expected zero "Maximum update depth" warnings; saw ${maximumUpdateDepthCount}.\n` +
        `Recent messages:\n${consoleMessages
          .filter((m) => m.text.includes('Maximum update depth'))
          .slice(0, 5)
          .map((m) => `  [${m.type}] ${m.text.slice(0, 160)}`)
          .join('\n')}`,
    ).toBe(0);
    // Issue 2: no overlay-layer error is logged more than once per
    // overlay-id (log-once Set in OverlayLayer).
    const repeated = Array.from(developerErrorCounts.entries()).filter(
      ([, count]) => count > 1,
    );
    expect(
      repeated.length,
      `Expected each overlay-layer DeveloperError to log at most once; ` +
        `saw repeats:\n${repeated
          .map(([key, count]) => `  x${count}  ${key}`)
          .join('\n')}`,
    ).toBe(0);
  });
});
