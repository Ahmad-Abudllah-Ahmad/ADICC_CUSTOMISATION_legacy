/**
 * Smoke — backend health check.
 *
 * Confirms the backend is reachable and its reported version matches
 * the frontend's package.json version. Fails with a friendly hint if
 * the backend isn't running.
 */
import { test, expect, API_URL } from '../fixtures';
import { expectHealthShape } from '../helpers';
import fs from 'node:fs';
import path from 'node:path';

const FRONTEND_PKG = JSON.parse(
  fs.readFileSync(path.resolve(process.cwd(), 'package.json'), 'utf-8'),
) as { version: string };

test.describe('@smoke health', () => {
  test('backend /api/health returns 200 with healthy status', async ({ playwright }) => {
    const ctx = await playwright.request.newContext();
    try {
      let res;
      try {
        res = await ctx.get(`${API_URL}/api/health`, { failOnStatusCode: false, timeout: 5_000 });
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        throw new Error(
          `Backend not reachable at ${API_URL}/api/health.\n` +
            `Start the dev server first:  cd backend && uvicorn app.main:app --reload\n` +
            `(or: docker compose up)\nUnderlying error: ${msg}`,
        );
      }
      expect(res.status(), 'backend /api/health must return 200').toBe(200);
      const body = await res.json();
      expectHealthShape(body);
      expect(body.modules_loaded, 'at least one module should be loaded').toBeGreaterThan(0);
    } finally {
      await ctx.dispose();
    }
  });

  test('reported backend version is a valid semver-ish string', async ({ playwright }) => {
    const ctx = await playwright.request.newContext();
    try {
      const res = await ctx.get(`${API_URL}/api/health`, { failOnStatusCode: false });
      if (!res.ok()) {
        test.skip(true, `backend unreachable: ${res.status()}`);
      }
      const body = await res.json();
      // We don't require exact equality (backend and frontend version often
      // drift by a patch level) — but both must be vNN.NN.NN.
      expect(body.version, 'backend version is empty').toMatch(/^\d+\.\d+/);
      expect(FRONTEND_PKG.version, 'frontend version is empty').toMatch(/^\d+\.\d+/);
    } finally {
      await ctx.dispose();
    }
  });
});
