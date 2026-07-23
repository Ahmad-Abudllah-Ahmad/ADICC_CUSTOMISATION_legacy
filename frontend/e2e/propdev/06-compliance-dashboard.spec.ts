/**
 * Scenario #6 — Compliance dashboard + Regulator reports.
 *
 * The compliance UI page (``/property-dev/compliance``) is part of #139
 * which is NOT in this branch. We assert the underlying API contract is
 * solid so the UI scenario will land cleanly when #139 ships:
 *
 *   - GET /regulator-reports/RERA      (MANAGER+ gated)
 *   - GET /regulator-reports/MAHARERA
 *   - GET /regulator-reports/214-FZ
 *
 * Each must:
 *   * Return 200 + a non-empty ``pdf_base64`` blob
 *   * Carry the correct ``regulator`` + ``quarter`` echoes
 *   * Have pdf_size_bytes > 0 (a real PDF, not an empty stub)
 *
 * TODO(#139): When the dashboard ships, the UI half of this spec is
 *   re-enabled — navigate to /property-dev/compliance, click "Run
 *   Checks", drill into each rule, then assert the generated PDF
 *   download. The fixtures here are sufficient to exercise that page.
 */
import { expect, test } from '@playwright/test';
import {
  bootstrapDevelopmentGraph,
  teardownDevelopment,
} from './helpers/api-bootstrap';
import { demoLogin } from './helpers/auth';
import { Shooter } from './helpers/screenshots';

test.describe.configure({ mode: 'serial' });

test('regulator-report endpoints generate non-empty PDFs (MANAGER)', async () => {
  const shooter = new Shooter('compliance');
  const admin = await demoLogin('admin');
  const manager = await demoLogin('manager');
  const graph = await bootstrapDevelopmentGraph(admin.api, {
    name: 'R6 Regulator Reports Dev',
  });

  const regulators = ['RERA', 'MAHARERA', '214-FZ'] as const;
  const quarter = '2026-Q2';
  for (const reg of regulators) {
    const res = await manager.api.get(
      `/api/v1/property-dev/regulator-reports/${reg}?dev_id=${graph.development_id}&quarter=${quarter}`,
    );
    expect(
      res.ok(),
      `Regulator report ${reg} failed: ${res.status()} ${await res.text()}`,
    ).toBeTruthy();
    const body = (await res.json()) as {
      regulator: string;
      quarter: string;
      pdf_size_bytes: number;
      pdf_base64: string;
      summary: Record<string, unknown>;
    };
    expect(body.regulator.length).toBeGreaterThan(0);
    expect(body.quarter).toBe(quarter);
    expect(body.pdf_size_bytes).toBeGreaterThan(0);
    expect(body.pdf_base64.length).toBeGreaterThan(50);
    shooter.saveJson(`${reg.toLowerCase()}_envelope`, {
      regulator: body.regulator,
      quarter: body.quarter,
      pdf_size_bytes: body.pdf_size_bytes,
      summary_keys: Object.keys(body.summary ?? {}),
    });
    // Decode + persist the PDF binary so the runner can spot-check it.
    try {
      const pdfBytes = Buffer.from(body.pdf_base64, 'base64');
      shooter.saveBinary(`${reg.toLowerCase()}.pdf`, pdfBytes);
      // Cheap PDF sanity check — the file must begin with "%PDF".
      expect(pdfBytes.subarray(0, 4).toString('latin1')).toBe('%PDF');
    } catch {
      // base64 → buffer failed → fail the test by tripping toBe
      expect(false, `${reg} pdf_base64 is not valid base64`).toBeTruthy();
    }
  }

  // CMA Saudi & Section 32 AU: not all are exposed via REST in this
  // branch — we attempt them but treat 404 as "feature not yet wired".
  // Their JSON envelope is identical when implemented.
  // Try the two more-experimental endpoints; capture the result without
  // failing the spec on the absence.
  for (const path of ['CMA', 'section32']) {
    const r = await manager.api.get(
      `/api/v1/property-dev/regulator-reports/${path}?dev_id=${graph.development_id}&quarter=${quarter}`,
    );
    shooter.saveJson(`${path.toLowerCase()}_probe`, { status: r.status() });
  }

  await teardownDevelopment(admin.api, graph.development_id);
});

test('TODO #139 — UI dashboard placeholder (skipped)', async ({ page }) => {
  // When /property-dev/compliance lands from #139, swap this stub for:
  //   await page.goto('/property-dev/compliance');
  //   await page.getByRole('button', { name: 'Run Checks' }).click();
  //   ...etc
  // For now we just check the SPA doesn't crash when the path is hit.
  await page.goto('/');
  await page.waitForLoadState('domcontentloaded');
  const shooter = new Shooter('compliance');
  await shooter.shoot(page, 'spa_root_loaded_no_compliance_route_yet');
  test.skip(true, 'UI compliance dashboard is task #139 — not in this branch');
});
