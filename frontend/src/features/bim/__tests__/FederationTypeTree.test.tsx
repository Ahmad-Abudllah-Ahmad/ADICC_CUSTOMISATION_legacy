// @ts-nocheck
/**
 * FederationTypeTree UI tests — v4.1 / BIM Federations Slice 2.
 *
 * The component renders the federation-flat element-type tree
 * (NOT per-model). These tests pin the contract:
 *   - loading / empty / error states surface explicit testids
 *   - rows render sorted by element_count DESC (mirrors backend sort)
 *   - expand/collapse toggles per-member breakdown
 *   - clicking a class row fires onSelectClass with the right args
 *
 * msw@2 intercepts fetch() so apiGet() round-trips against fixtures.
 * URL pattern: apiGet('/v1/bim-hub/...') → fetch('/api/v1/bim-hub/...')
 * (BASE_URL = '/api' from shared/lib/api.ts).
 */

import {
  describe,
  expect,
  it,
  vi,
  beforeAll,
  afterEach,
  afterAll,
} from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import React from 'react';

import { FederationTypeTree } from '../FederationTypeTree';

/* ── Fixtures ───────────────────────────────────────────────────────── */

const FED_ID = '11111111-1111-1111-1111-111111111111';

const POPULATED_TREE = {
  federation_id: FED_ID,
  total_elements: 17,
  classes: [
    {
      ifc_class: 'IfcWall',
      display_name: 'Wall',
      element_count: 12,
      sample_properties: ['FireRating', 'LoadBearing'],
      member_breakdown: [
        {
          model_id: 'm-struct',
          model_name: 'STRUCT',
          discipline: 'struct',
          element_count: 7,
        },
        {
          model_id: 'm-arch',
          model_name: 'ARCH',
          discipline: 'arch',
          element_count: 5,
        },
      ],
    },
    {
      ifc_class: 'IfcDoor',
      display_name: 'Door',
      element_count: 5,
      sample_properties: ['Material'],
      member_breakdown: [
        {
          model_id: 'm-mep',
          model_name: 'MEP',
          discipline: 'mep',
          element_count: 3,
        },
        {
          model_id: 'm-arch',
          model_name: 'ARCH',
          discipline: 'arch',
          element_count: 2,
        },
      ],
    },
  ],
};

const EMPTY_TREE = {
  federation_id: FED_ID,
  total_elements: 0,
  classes: [],
};

/* ── MSW server ─────────────────────────────────────────────────────── */

const TYPE_TREE_URL = `/api/v1/bim-hub/federations/${FED_ID}/type-tree`;

const populatedHandler = http.get(TYPE_TREE_URL, () =>
  HttpResponse.json(POPULATED_TREE),
);
const emptyHandler = http.get(TYPE_TREE_URL, () =>
  HttpResponse.json(EMPTY_TREE),
);
const errorHandler = http.get(TYPE_TREE_URL, () =>
  HttpResponse.json({ detail: 'boom' }, { status: 500 }),
);
const slowHandler = http.get(TYPE_TREE_URL, async () => {
  // Never resolve during the test — we'll inspect the loading state and
  // tear the server down before this would fire.
  await new Promise(() => undefined);
  return HttpResponse.json(EMPTY_TREE);
});

const server = setupServer();

// MSW v2's interceptor replaces ``globalThis.fetch`` when ``server.listen``
// runs — that swap discards the wrapper that ``src/test/setup.ts`` had
// installed to drop the realm-mismatched ``AbortSignal`` that jsdom hands
// to undici. Without re-wrapping post-MSW the production ``request()``
// helper trips undici's ``RequestInit.signal instanceof AbortSignal``
// check. See ``share-link.test.tsx`` for the same workaround.
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
afterEach(() => {
  server.resetHandlers();
});
afterAll(() => server.close());

/* ── Test helpers ───────────────────────────────────────────────────── */

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
    },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

/* ── Tests ──────────────────────────────────────────────────────────── */

describe('FederationTypeTree', () => {
  it('renders the loading state initially', () => {
    server.use(slowHandler);
    renderWithClient(<FederationTypeTree federationId={FED_ID} />);
    expect(
      screen.getByTestId('federation-type-tree-loading'),
    ).toBeInTheDocument();
  });

  it('renders empty-state when API returns no classes', async () => {
    server.use(emptyHandler);
    renderWithClient(<FederationTypeTree federationId={FED_ID} />);
    await waitFor(() =>
      expect(
        screen.getByTestId('federation-type-tree-empty'),
      ).toBeInTheDocument(),
    );
  });

  it('renders classes sorted by element_count desc', async () => {
    server.use(populatedHandler);
    renderWithClient(<FederationTypeTree federationId={FED_ID} />);
    await waitFor(() =>
      expect(screen.getByTestId('federation-type-tree')).toBeInTheDocument(),
    );
    const rows = screen.getAllByTestId(/^federation-type-tree-row-/);
    // The backend already sorts; the component preserves that order.
    expect(rows[0]).toHaveAttribute(
      'data-testid',
      'federation-type-tree-row-IfcWall',
    );
    expect(rows[1]).toHaveAttribute(
      'data-testid',
      'federation-type-tree-row-IfcDoor',
    );
    // Both badges visible with thousands-separator formatting.
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('expands/collapses a class to show per-member breakdown', async () => {
    server.use(populatedHandler);
    renderWithClient(<FederationTypeTree federationId={FED_ID} />);
    await waitFor(() =>
      expect(screen.getByTestId('federation-type-tree')).toBeInTheDocument(),
    );
    // Initially collapsed.
    expect(
      screen.queryByTestId('federation-type-tree-breakdown-IfcWall'),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByTestId('federation-type-tree-toggle-IfcWall'),
    );
    expect(
      screen.getByTestId('federation-type-tree-breakdown-IfcWall'),
    ).toBeInTheDocument();
    // Per-member rows render with model names.
    expect(
      screen.getByTestId('federation-type-tree-member-IfcWall-m-struct'),
    ).toHaveTextContent('STRUCT');
    expect(
      screen.getByTestId('federation-type-tree-member-IfcWall-m-arch'),
    ).toHaveTextContent('ARCH');

    // Collapse again.
    fireEvent.click(
      screen.getByTestId('federation-type-tree-toggle-IfcWall'),
    );
    expect(
      screen.queryByTestId('federation-type-tree-breakdown-IfcWall'),
    ).not.toBeInTheDocument();
  });

  it('clicking a class row fires onSelectClass with class + model ids', async () => {
    server.use(populatedHandler);
    const onSelect = vi.fn();
    renderWithClient(
      <FederationTypeTree federationId={FED_ID} onSelectClass={onSelect} />,
    );
    await waitFor(() =>
      expect(screen.getByTestId('federation-type-tree')).toBeInTheDocument(),
    );
    fireEvent.click(
      screen.getByTestId('federation-type-tree-select-IfcWall'),
    );
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith('IfcWall', ['m-struct', 'm-arch']);
  });

  it('renders the error state when the API fails', async () => {
    server.use(errorHandler);
    renderWithClient(<FederationTypeTree federationId={FED_ID} />);
    await waitFor(() =>
      expect(
        screen.getByTestId('federation-type-tree-error'),
      ).toBeInTheDocument(),
    );
  });

  it('shows sample_properties caption inside the expanded breakdown', async () => {
    server.use(populatedHandler);
    renderWithClient(<FederationTypeTree federationId={FED_ID} />);
    await waitFor(() =>
      expect(screen.getByTestId('federation-type-tree')).toBeInTheDocument(),
    );
    fireEvent.click(
      screen.getByTestId('federation-type-tree-toggle-IfcWall'),
    );
    expect(
      screen.getByTestId('federation-type-tree-breakdown-IfcWall'),
    ).toHaveTextContent(/FireRating/);
    expect(
      screen.getByTestId('federation-type-tree-breakdown-IfcWall'),
    ).toHaveTextContent(/LoadBearing/);
  });
});
