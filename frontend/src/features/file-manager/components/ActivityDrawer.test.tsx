// @ts-nocheck
/**
 * Unit tests for ``ActivityDrawer``.
 *
 * Covers the three states the drawer must always handle:
 *   1. Loaded list — rows render grouped by Today / Yesterday / Earlier.
 *   2. Error state — renders the retry button and clicking it refires
 *      the request (and succeeds the second time).
 *   3. Empty state — the explicit "no activity" panel renders when the
 *      API returns an empty list.
 *
 * The component fetches via ``apiGet`` from ``@/shared/lib/api``. We mock
 * that module directly rather than going through MSW because the project's
 * MSW + jsdom stack is flaky (see the parallel ``share-link.test.tsx``
 * which exhibits the same instability). Direct mocking keeps the test
 * deterministic and fast.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

// Mock apiGet BEFORE importing the component under test so the module
// graph picks up the mock instead of the real implementation.
vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
}));

import { apiGet } from '@/shared/lib/api';
import { ActivityDrawer, type ActivityEvent } from './ActivityDrawer';

/* ── Fixtures ──────────────────────────────────────────────────────── */

const DOCUMENT_ID = 'doc-abc';

/* The component buckets events relative to *local* midnight
   (``new Date(y, m, d)``), so a fixed offset like "1 hour ago" lands in
   "yesterday" whenever the suite runs just after midnight — the exact
   flake we're fixing. Anchor each fixture to the local start-of-day
   instead so it falls in its intended bucket regardless of the wall
   clock at run time:
     - today    → local noon today (always >= start-of-today)
     - yesterday→ local noon yesterday
     - earlier  → local noon three days ago
*/
function localStartOfToday(): number {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
}

function isoForBucket(daysAgo: number): string {
  // Noon of (today - daysAgo) in local time. Noon keeps us comfortably
  // away from both midnight boundaries so DST shifts can't tip the bucket.
  return new Date(localStartOfToday() - daysAgo * 24 * 3600 * 1000 + 12 * 3600 * 1000).toISOString();
}

/* Three events spanning Today / Yesterday / Earlier so the bucket
   labels are all exercised at once. */
const SAMPLE_EVENTS: ActivityEvent[] = [
  {
    id: 'ev-1',
    document_id: DOCUMENT_ID,
    user_id: 'user-1@example.com',
    action: 'renamed',
    meta: { old: 'a.pdf', new: 'b.pdf' },
    created_at: isoForBucket(0),
  },
  {
    id: 'ev-2',
    document_id: DOCUMENT_ID,
    user_id: 'user-2@example.com',
    action: 'uploaded',
    meta: { name: 'a.pdf' },
    created_at: isoForBucket(1),
  },
  {
    id: 'ev-3',
    document_id: DOCUMENT_ID,
    user_id: 'user-2@example.com',
    action: 'cde_state_changed',
    meta: { old: 'wip', new: 'shared' },
    created_at: isoForBucket(3),
  },
];

/* ── Helper ────────────────────────────────────────────────────────── */

function renderDrawer(overrides: { open?: boolean; documentId?: string | null } = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ActivityDrawer
        documentId={overrides.documentId ?? DOCUMENT_ID}
        documentName="spec.pdf"
        open={overrides.open ?? true}
        onClose={() => {}}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

/* ── Tests ─────────────────────────────────────────────────────────── */

describe('ActivityDrawer', () => {
  it('loads and renders the audit list with bucket sections', async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValueOnce(SAMPLE_EVENTS);
    renderDrawer();

    // All three rows from the fixture should be present after load.
    const rows = await screen.findAllByTestId('activity-row');
    expect(rows.length).toBe(SAMPLE_EVENTS.length);

    // All three bucket sections should render — one per fixture event.
    expect(screen.getByTestId('activity-bucket-today')).toBeInTheDocument();
    expect(screen.getByTestId('activity-bucket-yesterday')).toBeInTheDocument();
    expect(screen.getByTestId('activity-bucket-earlier')).toBeInTheDocument();
  });

  it('renders the empty state when the API returns no events', async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValueOnce([]);
    renderDrawer();

    expect(await screen.findByTestId('activity-empty')).toBeInTheDocument();
  });

  it('renders the error state and recovers when retry succeeds', async () => {
    // First call rejects, second resolves — clicking retry should
    // re-fire the request and surface the success branch.
    (apiGet as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(SAMPLE_EVENTS);

    renderDrawer();

    // Error UI renders with the retry button.
    expect(await screen.findByTestId('activity-error')).toBeInTheDocument();
    const retry = screen.getByTestId('activity-retry');
    expect(retry).toBeInTheDocument();

    fireEvent.click(retry);

    const rows = await screen.findAllByTestId('activity-row');
    expect(rows.length).toBe(SAMPLE_EVENTS.length);
  });

  it('tolerates the {items,total} envelope shape', async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      items: SAMPLE_EVENTS,
      total: SAMPLE_EVENTS.length,
    });
    renderDrawer();

    const rows = await screen.findAllByTestId('activity-row');
    expect(rows.length).toBe(SAMPLE_EVENTS.length);
  });

  it('does not fire the request when closed', async () => {
    renderDrawer({ open: false });

    // Give the (disabled) query a tick to confirm no request fires.
    await waitFor(() => {
      expect(apiGet).not.toHaveBeenCalled();
    });

    // No timeline UI should be rendered either — disabled drawer is off-screen.
    expect(screen.queryByTestId('activity-row')).toBeNull();
  });
});
