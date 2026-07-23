// @ts-nocheck
/**
 * Smart Views — typed API client tests.
 *
 * Intercepts the ``/api/v1/smart-views/`` surface with MSW so we exercise
 * the real ``shared/lib/api.ts`` request pipeline (JWT header injection,
 * 401 redirect, JSON serde) instead of mocking the helpers themselves.
 */
import { describe, it, expect, beforeAll, afterEach, afterAll } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import {
  listSmartViews,
  getSmartView,
  createSmartView,
  updateSmartView,
  deleteSmartView,
  evaluateSmartView,
  duplicateSmartView,
} from '../api';
import type {
  SmartViewCreatePayload,
  SmartViewResponse,
} from '../types';

const SAMPLE_VIEW: SmartViewResponse = {
  id: 'view-1',
  scope_type: 'user',
  scope_id: '00000000-0000-0000-0000-000000000001',
  name: 'Walls only',
  description: 'Show only walls',
  rules: [
    {
      id: 'r1',
      selector: {
        ifc_class: 'IfcWall',
        property: null,
        operator: null,
        value: null,
      },
      action: 'show',
      action_args: {},
      order: 0,
    },
  ],
  default_action: 'hide_all',
  color_legend: null,
  created_by: '00000000-0000-0000-0000-000000000001',
  created_at: '2026-05-21T00:00:00Z',
  updated_at: '2026-05-21T00:00:00Z',
};

let lastListUrl: string | null = null;
let lastEvalUrl: string | null = null;
let lastCreatePayload: unknown = null;
let lastUpdatePayload: unknown = null;

const server = setupServer(
  http.get('*/api/v1/smart-views/', ({ request }) => {
    lastListUrl = new URL(request.url).search;
    return HttpResponse.json([SAMPLE_VIEW]);
  }),
  http.get('*/api/v1/smart-views/:id', () => HttpResponse.json(SAMPLE_VIEW)),
  http.post('*/api/v1/smart-views/', async ({ request }) => {
    lastCreatePayload = await request.json();
    return HttpResponse.json(SAMPLE_VIEW, { status: 201 });
  }),
  http.put('*/api/v1/smart-views/:id', async ({ request }) => {
    lastUpdatePayload = await request.json();
    return HttpResponse.json({ ...SAMPLE_VIEW, name: 'Renamed' });
  }),
  http.delete('*/api/v1/smart-views/:id', () =>
    new HttpResponse(null, { status: 204 }),
  ),
  http.post('*/api/v1/smart-views/:id/evaluate', ({ request }) => {
    lastEvalUrl = new URL(request.url).search;
    return HttpResponse.json({
      states: {
        guid_1: { visible: true, color: '#ff0000', opacity: 1.0 },
      },
      legend: null,
      element_count: 1,
    });
  }),
);

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'warn' });
  // MSW v2 swaps `globalThis.fetch`; the global test setup's
  // realm-mismatch wrapper has already run by then, so re-wrap here.
  const mswFetch = globalThis.fetch;
  globalThis.fetch = ((input, init) => {
    if (init && 'signal' in init) {
      const { signal: _signal, ...rest } = init;
      return mswFetch(input, rest);
    }
    return mswFetch(input, init);
  }) as typeof fetch;
});
afterEach(() => {
  server.resetHandlers();
  lastListUrl = null;
  lastEvalUrl = null;
  lastCreatePayload = null;
  lastUpdatePayload = null;
});
afterAll(() => server.close());

describe('smart_views api client', () => {
  it('listSmartViews returns the array as-is', async () => {
    const views = await listSmartViews();
    expect(views).toHaveLength(1);
    expect(views[0]!.id).toBe('view-1');
  });

  it('listSmartViews forwards scopeType + scopeId as query params', async () => {
    await listSmartViews({ scopeType: 'project', scopeId: 'proj-1' });
    expect(lastListUrl).toContain('scope_type=project');
    expect(lastListUrl).toContain('scope_id=proj-1');
  });

  it('getSmartView fetches one by id', async () => {
    const view = await getSmartView('view-1');
    expect(view.name).toBe('Walls only');
  });

  it('createSmartView POSTs the payload and returns the server response', async () => {
    const payload: SmartViewCreatePayload = {
      name: 'New',
      description: null,
      rules: [],
      default_action: 'show_all',
      scope_type: 'user',
      scope_id: '00000000-0000-0000-0000-000000000001',
    };
    const created = await createSmartView(payload);
    expect(created.id).toBe('view-1');
    expect(lastCreatePayload).toMatchObject({ name: 'New', scope_type: 'user' });
  });

  it('updateSmartView PUTs the partial payload', async () => {
    const updated = await updateSmartView('view-1', { name: 'Renamed' });
    expect(updated.name).toBe('Renamed');
    expect(lastUpdatePayload).toEqual({ name: 'Renamed' });
  });

  it('deleteSmartView resolves on 204', async () => {
    await expect(deleteSmartView('view-1')).resolves.toBeUndefined();
  });

  it('evaluateSmartView appends model_id to the URL and parses the states map', async () => {
    const result = await evaluateSmartView('view-1', 'model-9');
    expect(lastEvalUrl).toContain('model_id=model-9');
    expect(result.element_count).toBe(1);
    expect(result.states.guid_1!.color).toBe('#ff0000');
  });

  it('duplicateSmartView creates a copy under the requested scope with a name suffix', async () => {
    const dup = await duplicateSmartView(SAMPLE_VIEW, {
      scopeType: 'project',
      scopeId: 'proj-9',
      nameSuffix: ' (clone)',
    });
    expect(dup.id).toBe('view-1');
    expect(lastCreatePayload).toMatchObject({
      name: 'Walls only (clone)',
      scope_type: 'project',
      scope_id: 'proj-9',
    });
  });
});
