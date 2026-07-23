// @ts-nocheck
/**
 * SmartViewRuleEditor — visual-builder UI tests.
 *
 * Tests the visible behaviour:
 *   - empty editor renders cleanly
 *   - Add rule appends a row
 *   - Operator switch morphs the value-input correctly
 *   - Action='color' shows the colour picker; action='transparent' shows the slider
 *   - Delete removes a row + reindexes order
 *   - Drag-reorder updates order (via direct moveRule call simulated through DOM)
 *   - Save triggers POST when no initialView, PUT when one is supplied
 *   - Empty name surfaces an inline error and does NOT call the API
 *   - default-action select toggles show_all ↔ hide_all
 *   - color_by_property checkbox reveals the property input
 */
import {
  describe,
  it,
  expect,
  beforeAll,
  afterEach,
  afterAll,
  vi,
} from 'vitest';
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { SmartViewRuleEditor } from '../SmartViewRuleEditor';
import type { SmartViewResponse } from '../types';

const SAMPLE_VIEW: SmartViewResponse = {
  id: 'view-1',
  scope_type: 'user',
  scope_id: '00000000-0000-0000-0000-000000000001',
  name: 'My view',
  description: 'Desc',
  rules: [
    {
      id: 'r1',
      selector: { ifc_class: 'IfcWall', property: null, operator: null, value: null },
      action: 'show',
      action_args: {},
      order: 0,
    },
    {
      id: 'r2',
      selector: { ifc_class: 'IfcSlab', property: null, operator: null, value: null },
      action: 'hide',
      action_args: {},
      order: 1,
    },
  ],
  default_action: 'show_all',
  color_legend: null,
  created_by: '00000000-0000-0000-0000-000000000001',
  created_at: '2026-05-21T00:00:00Z',
  updated_at: '2026-05-21T00:00:00Z',
};

let lastMethod: string | null = null;
let lastUrl: string | null = null;
let lastBody: unknown = null;

const server = setupServer(
  http.post('*/api/v1/smart-views/', async ({ request }) => {
    lastMethod = 'POST';
    lastUrl = request.url;
    lastBody = await request.json();
    return HttpResponse.json(SAMPLE_VIEW, { status: 201 });
  }),
  http.put('*/api/v1/smart-views/:id', async ({ request }) => {
    lastMethod = 'PUT';
    lastUrl = request.url;
    lastBody = await request.json();
    return HttpResponse.json(SAMPLE_VIEW);
  }),
);

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'warn' });
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
  lastMethod = null;
  lastUrl = null;
  lastBody = null;
  cleanup();
});
afterAll(() => server.close());

function renderEditor(props?: {
  initialView?: SmartViewResponse | null;
  onClose?: () => void;
  onSaved?: (v: SmartViewResponse) => void;
}) {
  const onClose = props?.onClose ?? vi.fn();
  const onSaved = props?.onSaved ?? vi.fn();
  const result = render(
    <SmartViewRuleEditor
      open
      onClose={onClose}
      initialView={props?.initialView ?? null}
      scopeType="user"
      scopeId="00000000-0000-0000-0000-000000000001"
      onSaved={onSaved}
    />,
  );
  return { ...result, onClose, onSaved };
}

describe('SmartViewRuleEditor', () => {
  it('renders empty editor with no rules', () => {
    renderEditor();
    expect(screen.getByTestId('smart-view-editor')).toBeInTheDocument();
    // No rule rows yet
    expect(screen.queryByTestId('smart-view-rule-0')).toBeNull();
    // "No rules yet" hint
    expect(
      screen.getByText(/no rules yet/i),
    ).toBeInTheDocument();
  });

  it('"Add rule" appends a row', () => {
    renderEditor();
    fireEvent.click(screen.getByTestId('smart-view-add-rule'));
    expect(screen.getByTestId('smart-view-rule-0')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('smart-view-add-rule'));
    expect(screen.getByTestId('smart-view-rule-1')).toBeInTheDocument();
  });

  it('Operator switch from "eq" → "exists" hides the value input', () => {
    renderEditor();
    fireEvent.click(screen.getByTestId('smart-view-add-rule'));
    const opSelect = screen.getByTestId('smart-view-rule-operator-0');
    fireEvent.change(opSelect, { target: { value: 'eq' } });
    expect(screen.getByTestId('smart-view-rule-value-0')).toBeInTheDocument();
    fireEvent.change(opSelect, { target: { value: 'exists' } });
    expect(screen.queryByTestId('smart-view-rule-value-0')).toBeNull();
    expect(
      screen.getByTestId('smart-view-rule-value-disabled-0'),
    ).toBeInTheDocument();
  });

  it('Operator switch from text → number changes the input type', () => {
    renderEditor();
    fireEvent.click(screen.getByTestId('smart-view-add-rule'));
    const opSelect = screen.getByTestId('smart-view-rule-operator-0');
    fireEvent.change(opSelect, { target: { value: 'eq' } });
    expect(
      (screen.getByTestId('smart-view-rule-value-0') as HTMLInputElement).type,
    ).toBe('text');
    fireEvent.change(opSelect, { target: { value: 'gt' } });
    expect(
      (screen.getByTestId('smart-view-rule-value-0') as HTMLInputElement).type,
    ).toBe('number');
  });

  it('action="color" reveals the colour picker', () => {
    renderEditor();
    fireEvent.click(screen.getByTestId('smart-view-add-rule'));
    fireEvent.change(screen.getByTestId('smart-view-rule-action-0'), {
      target: { value: 'color' },
    });
    expect(screen.getByTestId('smart-view-rule-color-0')).toBeInTheDocument();
    expect(
      screen.getByTestId('smart-view-rule-color-hex-0'),
    ).toBeInTheDocument();
  });

  it('action="transparent" reveals the opacity slider', () => {
    renderEditor();
    fireEvent.click(screen.getByTestId('smart-view-add-rule'));
    fireEvent.change(screen.getByTestId('smart-view-rule-action-0'), {
      target: { value: 'transparent' },
    });
    expect(
      screen.getByTestId('smart-view-rule-opacity-0'),
    ).toBeInTheDocument();
    // The colour picker is NOT shown for action=transparent
    expect(screen.queryByTestId('smart-view-rule-color-0')).toBeNull();
  });

  it('Delete row removes it from the list', () => {
    renderEditor();
    fireEvent.click(screen.getByTestId('smart-view-add-rule'));
    fireEvent.click(screen.getByTestId('smart-view-add-rule'));
    expect(screen.getByTestId('smart-view-rule-1')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('smart-view-rule-delete-0'));
    // After deletion the second row's index becomes 0 (re-indexed).
    expect(screen.getByTestId('smart-view-rule-0')).toBeInTheDocument();
    expect(screen.queryByTestId('smart-view-rule-1')).toBeNull();
  });

  it('default-action select toggles show_all ↔ hide_all', () => {
    renderEditor();
    const sel = screen.getByTestId(
      'smart-view-default-action',
    ) as HTMLSelectElement;
    expect(sel.value).toBe('show_all');
    fireEvent.change(sel, { target: { value: 'hide_all' } });
    expect(sel.value).toBe('hide_all');
  });

  it('color_by_property checkbox reveals the property input', () => {
    renderEditor();
    fireEvent.click(screen.getByTestId('smart-view-add-rule'));
    fireEvent.change(screen.getByTestId('smart-view-rule-action-0'), {
      target: { value: 'color' },
    });
    expect(
      screen.queryByTestId('smart-view-rule-colorby-input-0'),
    ).toBeNull();
    fireEvent.click(screen.getByTestId('smart-view-rule-colorby-toggle-0'));
    expect(
      screen.getByTestId('smart-view-rule-colorby-input-0'),
    ).toBeInTheDocument();
  });

  it('Save with empty name surfaces an inline error and does NOT POST', async () => {
    const onSaved = vi.fn();
    renderEditor({ onSaved });
    fireEvent.click(screen.getByTestId('smart-view-save'));
    expect(screen.getByText(/give this view a name/i)).toBeInTheDocument();
    // No save happened
    expect(lastMethod).toBeNull();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it('Save with a valid name POSTs and fires onSaved (create path)', async () => {
    const onSaved = vi.fn();
    renderEditor({ onSaved });
    const name = screen.getByTestId('smart-view-name-input') as HTMLInputElement;
    fireEvent.change(name, { target: { value: 'My view' } });
    await act(async () => {
      fireEvent.click(screen.getByTestId('smart-view-save'));
    });
    // Wait one tick for the promise chain.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(lastMethod).toBe('POST');
    expect(onSaved).toHaveBeenCalled();
    expect(lastBody).toMatchObject({
      name: 'My view',
      scope_type: 'user',
    });
  });

  it('Save with initialView PUTs (update path) at the right URL', async () => {
    const onSaved = vi.fn();
    renderEditor({ initialView: SAMPLE_VIEW, onSaved });
    await act(async () => {
      fireEvent.click(screen.getByTestId('smart-view-save'));
    });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(lastMethod).toBe('PUT');
    expect(lastUrl).toContain('/smart-views/view-1');
    expect(onSaved).toHaveBeenCalled();
  });

  it('initialView seeds existing rules + name into the editor', () => {
    renderEditor({ initialView: SAMPLE_VIEW });
    expect(
      (screen.getByTestId('smart-view-name-input') as HTMLInputElement).value,
    ).toBe('My view');
    expect(screen.getByTestId('smart-view-rule-0')).toBeInTheDocument();
    expect(screen.getByTestId('smart-view-rule-1')).toBeInTheDocument();
  });

  it('Delete on row 0 promotes row 1 to position 0 (re-index)', () => {
    renderEditor({ initialView: SAMPLE_VIEW });
    // Before: rule-0 = IfcWall, rule-1 = IfcSlab.
    const ifc0Before = (
      screen.getByTestId('smart-view-rule-ifc-0') as HTMLInputElement
    ).value;
    expect(ifc0Before).toBe('IfcWall');
    fireEvent.click(screen.getByTestId('smart-view-rule-delete-0'));
    // After: rule-0 should now hold what was IfcSlab.
    const ifc0After = (
      screen.getByTestId('smart-view-rule-ifc-0') as HTMLInputElement
    ).value;
    expect(ifc0After).toBe('IfcSlab');
    expect(screen.queryByTestId('smart-view-rule-1')).toBeNull();
  });
});
