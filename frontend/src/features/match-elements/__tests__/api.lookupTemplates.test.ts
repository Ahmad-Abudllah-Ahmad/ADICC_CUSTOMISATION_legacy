// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
//
// URL-contract test for matchElementsApi.lookupTemplates.
//
// The wizard uses this to ask, before running a search, which group
// signatures the team already confirmed a code for ("previously matched"
// hint). The request path and body are load-bearing: the backend runs
// with redirect_slashes=False, so /templates/lookup must be hit exactly,
// with a POST carrying { signatures: [...] }.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@/stores/useAuthStore', () => {
  const token = 'test-token';
  return {
    useAuthStore: Object.assign(
      (selector: (s: { accessToken: string }) => unknown) =>
        selector({ accessToken: token }),
      { getState: () => ({ accessToken: token }) },
    ),
  };
});

import { matchElementsApi, type TemplateLookupResponse } from '../api';

interface FetchCall {
  url: string;
  init: RequestInit | undefined;
}

const calls: FetchCall[] = [];

function stubFetch(payload: unknown, ok = true): void {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    return {
      ok,
      status: ok ? 200 : 500,
      statusText: ok ? 'OK' : 'Error',
      json: async () => payload,
    } as unknown as Response;
  });
  vi.stubGlobal('fetch', fetchMock);
}

beforeEach(() => {
  calls.length = 0;
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('matchElementsApi.lookupTemplates', () => {
  it('POSTs /api/v1/match_elements/templates/lookup with the signatures body', async () => {
    const payload: TemplateLookupResponse = { matches: {} };
    stubFetch(payload);

    await matchElementsApi.lookupTemplates(['sig-a', 'sig-b']);

    expect(calls).toHaveLength(1);
    const { url, init } = calls[0]!;
    expect(url).toBe('/api/v1/match_elements/templates/lookup');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({
      signatures: ['sig-a', 'sig-b'],
    });
    // Auth header is threaded through the shared caller.
    const headers = init?.headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer test-token');
  });

  it('returns the parsed signature -> template map', async () => {
    const template = {
      id: 'tmpl-1',
      tenant_id: null,
      signature: 'sig-a',
      label: 'IfcWall - concrete - 240mm',
      cwicr_position_id: 'ci-1',
      source_fields: ['ifc_class', 'material'],
      use_count: 3,
      last_used_at: null,
      created_at: '2026-07-01T00:00:00Z',
    };
    stubFetch({ matches: { 'sig-a': template } } satisfies TemplateLookupResponse);

    const res = await matchElementsApi.lookupTemplates(['sig-a']);

    expect(res.matches['sig-a']?.cwicr_position_id).toBe('ci-1');
    expect(res.matches['sig-a']?.use_count).toBe(3);
    // A signature with no confirmed mapping is simply absent.
    expect(res.matches['sig-unknown']).toBeUndefined();
  });
});
