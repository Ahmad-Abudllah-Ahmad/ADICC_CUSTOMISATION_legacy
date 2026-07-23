// @ts-nocheck
/**
 * useFederatedGeometryLoader tests — BIM Federations Slice 3.
 *
 * Counter-intuitive design note
 * -----------------------------
 * MSW v2 swaps ``globalThis.fetch`` when ``server.listen`` runs, which
 * discards the AbortSignal wrapper installed in ``src/test/setup.ts``.
 * We re-install the wrapper post-listen so the production ``apiGet``
 * (which always attaches a signal) doesn't trip undici's realm check.
 * See FederationTypeTree.test.tsx for the same workaround.
 */
import {
  describe,
  expect,
  it,
  vi,
  beforeAll,
  beforeEach,
  afterEach,
  afterAll,
} from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import React from 'react';

import { useFederatedGeometryLoader } from '../useFederatedGeometryLoader';
import { useAuthStore } from '@/stores/useAuthStore';

/* ── Fixtures ───────────────────────────────────────────────────────── */

const FED_ID = '22222222-2222-2222-2222-222222222222';

const DETAIL = {
  id: FED_ID,
  project_id: 'proj-1',
  name: 'Mock federation',
  description: null,
  origin_offset: { x: 0, y: 0, z: 0 },
  shared_units: 'm',
  member_count: 2,
  members: [
    {
      id: 'mem-1',
      federation_id: FED_ID,
      bim_model_id: 'mod-arch',
      discipline: 'arch',
      visible: true,
      z_order: 0,
      color_hint: null,
    },
    {
      id: 'mem-2',
      federation_id: FED_ID,
      bim_model_id: 'mod-struct',
      discipline: 'struct',
      visible: true,
      z_order: 1,
      color_hint: null,
    },
  ],
};

/* ── MSW server ─────────────────────────────────────────────────────── */

const DETAIL_URL = `/api/v1/bim-hub/federations/${FED_ID}`;
const GEOM_URL_ARCH = '/api/v1/bim-hub/models/mod-arch/geometry/';
const GEOM_URL_STRUCT = '/api/v1/bim-hub/models/mod-struct/geometry/';

// Capture headers from every geometry fetch so we can assert auth.
const seenHeaders: Record<string, Record<string, string>> = {};

function geometryHandler(modelId: string, url: string, opts: { status?: number } = {}) {
  return http.get(url, ({ request }) => {
    const captured: Record<string, string> = {};
    request.headers.forEach((v, k) => {
      captured[k.toLowerCase()] = v;
    });
    seenHeaders[modelId] = captured;
    if (opts.status && opts.status >= 400) {
      return HttpResponse.json(
        { detail: `mock ${opts.status}` },
        { status: opts.status },
      );
    }
    // Pretend GLB — just a few bytes so the ArrayBuffer assertion has
    // something to look at.
    const bytes = new Uint8Array([0x67, 0x6c, 0x54, 0x46, 0x02, 0x00, 0x00, 0x00]);
    return new HttpResponse(bytes, {
      status: 200,
      headers: { 'Content-Type': 'model/gltf-binary' },
    });
  });
}

const server = setupServer();

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' });
  const mswFetch = globalThis.fetch;
  globalThis.fetch = ((input, init) => {
    if (init && 'signal' in init) {
      const { signal: _signal, ...rest } = init;
      return mswFetch(input, rest);
    }
    return mswFetch(input, init);
  }) as typeof fetch;
});

beforeEach(() => {
  for (const k of Object.keys(seenHeaders)) delete seenHeaders[k];
  // Reset auth state — useAuthStore is a zustand store; setState directly.
  useAuthStore.setState({
    accessToken: null,
    isAuthenticated: false,
    userEmail: null,
    userRole: null,
  });
});

afterEach(() => {
  server.resetHandlers();
});

afterAll(() => server.close());

/* ── Helpers ────────────────────────────────────────────────────────── */

function wrap() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

/* ── Tests ──────────────────────────────────────────────────────────── */

describe('useFederatedGeometryLoader', () => {
  it('returns isLoading=true initially', () => {
    // Use a handler that never resolves so the test sees the initial
    // loading state before any data arrives.
    server.use(
      http.get(DETAIL_URL, async () => {
        await new Promise(() => undefined);
        return HttpResponse.json(DETAIL);
      }),
    );
    const { result } = renderHook(() => useFederatedGeometryLoader(FED_ID), {
      wrapper: wrap(),
    });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.detail).toBeUndefined();
    expect(result.current.members).toEqual([]);
  });

  it('fires N parallel geometry queries after detail resolves', async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(DETAIL)),
      geometryHandler('mod-arch', GEOM_URL_ARCH),
      geometryHandler('mod-struct', GEOM_URL_STRUCT),
    );
    const { result } = renderHook(() => useFederatedGeometryLoader(FED_ID), {
      wrapper: wrap(),
    });
    await waitFor(() => {
      expect(result.current.members.length).toBe(2);
    });
    expect(result.current.detail?.id).toBe(FED_ID);
    expect(result.current.errors).toEqual([]);
    const ids = result.current.members.map((m) => m.modelId).sort();
    expect(ids).toEqual(['mod-arch', 'mod-struct']);
    // Each member's buffer is an ArrayBuffer with bytes.
    for (const m of result.current.members) {
      expect(m.buffer).toBeInstanceOf(ArrayBuffer);
      expect(m.buffer.byteLength).toBeGreaterThan(0);
    }
    // Both endpoints were actually hit.
    expect(seenHeaders['mod-arch']).toBeDefined();
    expect(seenHeaders['mod-struct']).toBeDefined();
  });

  it('per-member 404 surfaces only on that member, others still load', async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(DETAIL)),
      geometryHandler('mod-arch', GEOM_URL_ARCH, { status: 404 }),
      geometryHandler('mod-struct', GEOM_URL_STRUCT),
    );
    const { result } = renderHook(() => useFederatedGeometryLoader(FED_ID), {
      wrapper: wrap(),
    });
    await waitFor(() => {
      // One member loaded successfully.
      expect(result.current.members.length).toBe(1);
      // One error surfaced for the bad one.
      expect(result.current.errors.length).toBe(1);
    });
    expect(result.current.members[0].modelId).toBe('mod-struct');
    expect(result.current.errors[0].modelId).toBe('mod-arch');
    expect(result.current.errors[0].error.message).toMatch(/404|mock/);
    // A 404 is flagged as "no geometry yet" (informational), not a hard
    // failure, and carries a display name for the viewer.
    expect(result.current.errors[0].noGeometry).toBe(true);
    expect(result.current.errors[0].error.message).toMatch(/no 3D geometry yet/);
    expect(result.current.errors[0].modelName).toBe('mod-arch'.slice(0, 8));
  });

  it('a non-404 geometry error stays a hard failure (noGeometry=false)', async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(DETAIL)),
      geometryHandler('mod-arch', GEOM_URL_ARCH, { status: 500 }),
      geometryHandler('mod-struct', GEOM_URL_STRUCT),
    );
    const { result } = renderHook(() => useFederatedGeometryLoader(FED_ID), {
      wrapper: wrap(),
    });
    await waitFor(() => {
      expect(result.current.members.length).toBe(1);
      expect(result.current.errors.length).toBe(1);
    });
    expect(result.current.errors[0].modelId).toBe('mod-arch');
    expect(result.current.errors[0].noGeometry).toBe(false);
    expect(result.current.errors[0].error.message).toMatch(/failed/i);
  });

  it('attaches Authorization: Bearer to every geometry query when a token is present', async () => {
    useAuthStore.setState({
      accessToken: 'test-jwt-token',
      isAuthenticated: true,
      userEmail: 'a@b.c',
      userRole: 'admin',
    });
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(DETAIL)),
      geometryHandler('mod-arch', GEOM_URL_ARCH),
      geometryHandler('mod-struct', GEOM_URL_STRUCT),
    );
    const { result } = renderHook(() => useFederatedGeometryLoader(FED_ID), {
      wrapper: wrap(),
    });
    await waitFor(() => expect(result.current.members.length).toBe(2));
    expect(seenHeaders['mod-arch'].authorization).toBe('Bearer test-jwt-token');
    expect(seenHeaders['mod-struct'].authorization).toBe(
      'Bearer test-jwt-token',
    );
    // Both also got the DDC client marker.
    expect(seenHeaders['mod-arch']['x-ddc-client']).toBe('OE/1.0');
  });
});
