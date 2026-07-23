/**
 * seed.fixture.ts — fresh demo data state.
 *
 * Calls POST /api/v1/admin/seed-demo to (re)create the canonical demo
 * project and reference data. Idempotent on the backend side — if the
 * demo seed already exists, the endpoint returns 200 with no changes.
 *
 * The seed runs at WORKER scope so we don't re-seed 1000 times across
 * a 1000-test suite. Tests that mutate the demo data should use the
 * `project` fixture from tenant.fixture.ts (per-test isolated).
 *
 * Falls back gracefully when the endpoint isn't implemented (404/501).
 * In that case the fixture is a no-op and tests assume the demo data
 * was pre-seeded by `make seed` on the dev machine.
 */
import { test as base } from './screenshot.fixture';

type SeedFixtures = {
  seededDemoData: { ok: boolean; seeded: boolean; note?: string };
};

export const test = base.extend<SeedFixtures, { workerSeed: { ok: boolean; seeded: boolean; note?: string } }>({
  workerSeed: [
    async ({ playwright, accessToken }, use) => {
      const apiUrl = process.env.OE_TEST_API_URL ?? 'http://localhost:8000';
      const ctx = await playwright.request.newContext();
      let result: { ok: boolean; seeded: boolean; note?: string };
      try {
        const res = await ctx.post(`${apiUrl}/api/v1/admin/seed-demo`, {
          headers: {
            Authorization: `Bearer ${accessToken}`,
            Accept: 'application/json',
            'Content-Type': 'application/json',
            'X-DDC-Client': 'OE-QA/1.0',
          },
          failOnStatusCode: false,
          data: {},
        });
        if (res.ok()) {
          result = { ok: true, seeded: true };
        } else if (res.status() === 404 || res.status() === 501) {
          result = { ok: true, seeded: false, note: `seed endpoint missing (${res.status()})` };
        } else {
          result = {
            ok: false,
            seeded: false,
            note: `seed failed: ${res.status()} ${(await res.text()).slice(0, 200)}`,
          };
        }
      } finally {
        await ctx.dispose();
      }
      await use(result);
    },
    { scope: 'worker' },
  ],

  seededDemoData: async ({ workerSeed }, use) => {
    await use(workerSeed);
  },
});

export { expect } from '@playwright/test';
