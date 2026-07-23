/**
 * api.fixture.ts — typed API client for setup/teardown.
 *
 * Mirrors the request/response patterns from `frontend/src/shared/lib/api.ts`
 * (Bearer token, JSON, X-DDC-Client header) but runs from the test process
 * via Playwright's APIRequestContext — so no browser overhead and no
 * UI clicks needed for fixture seeding.
 *
 * Usage:
 *   import { test, expect } from './api.fixture';
 *   test('creates project via API', async ({ api }) => {
 *     const project = await api.post<Project>('/projects/', { name: 'X' });
 *     expect(project.id).toBeTruthy();
 *   });
 */
import { test as base, type APIRequestContext, type APIResponse } from '@playwright/test';
import { test as authTest } from './auth.fixture';

const API_URL = process.env.OE_TEST_API_URL ?? 'http://localhost:8000';

export interface TypedApiClient {
  get<T = unknown>(path: string, init?: { params?: Record<string, string> }): Promise<T>;
  post<T = unknown>(path: string, body?: unknown): Promise<T>;
  put<T = unknown>(path: string, body?: unknown): Promise<T>;
  patch<T = unknown>(path: string, body?: unknown): Promise<T>;
  delete<T = unknown>(path: string): Promise<T>;
  /** Raw access — caller handles the response. Use for non-200 expectations. */
  raw(method: string, path: string, body?: unknown): Promise<APIResponse>;
}

function buildPath(path: string, params?: Record<string, string>): string {
  // Accept both `/projects/` (joined to /api/v1) and absolute `/api/v1/...`.
  const norm = path.startsWith('/api/') ? path : `/api/v1${path.startsWith('/') ? '' : '/'}${path}`;
  const url = new URL(`${API_URL}${norm}`);
  if (params) {
    for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  }
  return url.toString();
}

function makeClient(ctx: APIRequestContext, token: string): TypedApiClient {
  const headers = (): Record<string, string> => ({
    Authorization: `Bearer ${token}`,
    Accept: 'application/json',
    'Content-Type': 'application/json',
    'X-DDC-Client': 'OE-QA/1.0',
  });

  const send = async (method: string, path: string, body?: unknown, params?: Record<string, string>): Promise<APIResponse> => {
    const url = buildPath(path, params);
    const init = { headers: headers(), failOnStatusCode: false, data: body };
    switch (method) {
      case 'GET':
        return ctx.get(url, { headers: headers(), failOnStatusCode: false });
      case 'POST':
        return ctx.post(url, init);
      case 'PUT':
        return ctx.put(url, init);
      case 'PATCH':
        return ctx.patch(url, init);
      case 'DELETE':
        return ctx.delete(url, { headers: headers(), failOnStatusCode: false });
      default:
        throw new Error(`api.fixture: unsupported method ${method}`);
    }
  };

  const asJson = async <T>(res: APIResponse, method: string, path: string): Promise<T> => {
    if (!res.ok()) {
      const text = await res.text().catch(() => '');
      throw new Error(`api.fixture: ${method} ${path} → ${res.status()} ${text.slice(0, 240)}`);
    }
    if (res.status() === 204) return undefined as T;
    try {
      return (await res.json()) as T;
    } catch {
      return undefined as T;
    }
  };

  return {
    async get<T>(path: string, init?: { params?: Record<string, string> }): Promise<T> {
      return asJson<T>(await send('GET', path, undefined, init?.params), 'GET', path);
    },
    async post<T>(path: string, body?: unknown): Promise<T> {
      return asJson<T>(await send('POST', path, body), 'POST', path);
    },
    async put<T>(path: string, body?: unknown): Promise<T> {
      return asJson<T>(await send('PUT', path, body), 'PUT', path);
    },
    async patch<T>(path: string, body?: unknown): Promise<T> {
      return asJson<T>(await send('PATCH', path, body), 'PATCH', path);
    },
    async delete<T>(path: string): Promise<T> {
      return asJson<T>(await send('DELETE', path), 'DELETE', path);
    },
    raw(method: string, path: string, body?: unknown) {
      return send(method.toUpperCase(), path, body);
    },
  };
}

type ApiFixtures = {
  api: TypedApiClient;
};

export const test = authTest.extend<ApiFixtures>({
  api: async ({ playwright, accessToken }, use) => {
    const ctx = await playwright.request.newContext();
    try {
      await use(makeClient(ctx, accessToken));
    } finally {
      await ctx.dispose();
    }
  },
});

export { expect } from '@playwright/test';
export { API_URL };
