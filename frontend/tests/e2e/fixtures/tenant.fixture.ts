/**
 * tenant.fixture.ts — per-test isolated project (no test pollution).
 *
 * Each test that requests `project` gets a fresh project created via API.
 * The fixture also tears down the project after the test (best-effort —
 * a failed delete doesn't fail the test, only logs).
 *
 * For tests that need to reuse the demo project (e.g. read-only checks),
 * import the `demoProject` fixture which fetches the first existing
 * project owned by the demo user.
 */
import { test as apiTest, type TypedApiClient } from './api.fixture';
import type { TestInfo } from '@playwright/test';

export interface Project {
  id: string;
  name: string;
  currency?: string;
  [k: string]: unknown;
}

async function createProject(api: TypedApiClient, name: string): Promise<Project> {
  return api.post<Project>('/projects/', {
    name,
    description: `E2E auto-created — ${name}`,
    currency: 'EUR',
  });
}

async function deleteProject(api: TypedApiClient, id: string): Promise<void> {
  await api.raw('DELETE', `/projects/${id}/`);
}

async function firstProject(api: TypedApiClient): Promise<Project | null> {
  const res = await api.raw('GET', '/projects/');
  if (!res.ok()) return null;
  const body = (await res.json()) as Project[] | { items: Project[] };
  const list = Array.isArray(body) ? body : body.items ?? [];
  return list[0] ?? null;
}

type TenantFixtures = {
  project: Project;
  demoProject: Project;
};

export const test = apiTest.extend<TenantFixtures>({
  project: async ({ api }, use, testInfo: TestInfo) => {
    const stamp = `${testInfo.workerIndex}-${Date.now().toString(36)}`;
    const name = `E2E ${testInfo.title.slice(0, 40)} ${stamp}`;
    const created = await createProject(api, name);
    try {
      await use(created);
    } finally {
      await deleteProject(api, created.id).catch(() => {
        /* swallow — orphaned projects get cleaned by nightly seed reset */
      });
    }
  },

  demoProject: async ({ api }, use) => {
    let existing = await firstProject(api);
    if (!existing) {
      existing = await createProject(api, 'E2E Demo Fallback');
    }
    await use(existing);
  },
});

export { expect } from '@playwright/test';
