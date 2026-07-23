// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Empty / error-state tests for the Portfolio / multi-project page.
//
// These complement PortfolioPage.test.tsx (which covers the happy path: tree
// renders, pick-a-node prompt, and a successful cross-project CPM) by exercising
// the surfaces a smoke test skips:
//   - the empty portfolio tree (no nodes yet),
//   - the tree load-error recovery (the tree query rejects),
//   - the CPM load-error recovery for a picked node (the CPM query rejects).
//
// Both API layers the page depends on are automocked (no factory) so every
// export is a vi.fn(); return values are configured per test. A partial factory
// of a shared api module would risk bleeding across the suite, so we automock.
//
// React Query runs with retry disabled so the error states surface immediately.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

vi.mock('./portfolioCpmApi');
vi.mock('@/features/schedule/api');

import { portfolioCpmApi } from './portfolioCpmApi';
import { scheduleApi } from '@/features/schedule/api';
import { PortfolioPage } from './PortfolioPage';

type AnyFn = ReturnType<typeof vi.fn>;

const NODE_ID = '11111111-1111-1111-1111-111111111111';

const sampleTree = [
  {
    id: NODE_ID,
    parent_id: null,
    node_type: 'portfolio',
    name: 'North Region Portfolio',
    code: 'NRP',
    sort_order: 0,
    project_ids: ['p1', 'p2'],
    children: [],
  },
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PortfolioPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PortfolioPage empty / error states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Sensible defaults; individual tests override the call under test.
    (portfolioCpmApi.getTree as AnyFn).mockResolvedValue([]);
    (portfolioCpmApi.nodeCpm as AnyFn).mockResolvedValue(undefined);
    // No active project in the store, so the cross-links panel shows its
    // "pick a project" empty state and never calls the schedule API.
    (scheduleApi.listSchedules as AnyFn).mockResolvedValue([]);
    (scheduleApi.getGantt as AnyFn).mockResolvedValue({ activities: [] });
  });

  it('shows the empty-tree state when there are no portfolio nodes', async () => {
    (portfolioCpmApi.getTree as AnyFn).mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText(/No portfolios yet/i)).toBeInTheDocument();
    // With no node selected, the CPM panel prompts to pick a node and never fetches.
    expect(screen.getByText(/Pick a node/i)).toBeInTheDocument();
    expect(portfolioCpmApi.nodeCpm).not.toHaveBeenCalled();
  });

  it('renders the tree load-error recovery when the tree query fails', async () => {
    (portfolioCpmApi.getTree as AnyFn).mockRejectedValue(new Error('tree boom'));
    renderPage();
    // RecoveryCard exposes a retry affordance; assert it offers to try again.
    expect(await screen.findByRole('button', { name: /retry/i })).toBeInTheDocument();
    // The tree list never rendered.
    expect(screen.queryByTestId('portfolio-tree-list')).not.toBeInTheDocument();
  });

  it('renders the CPM load-error recovery when a picked node fails to analyse', async () => {
    (portfolioCpmApi.getTree as AnyFn).mockResolvedValue(sampleTree);
    (portfolioCpmApi.nodeCpm as AnyFn).mockRejectedValue(new Error('cpm boom'));
    renderPage();

    const list = await screen.findByTestId('portfolio-tree-list');
    fireEvent.click(within(list).getByText('North Region Portfolio'));

    await waitFor(() => expect(portfolioCpmApi.nodeCpm).toHaveBeenCalledWith(NODE_ID));
    // The CPM result panel is replaced by a retry-able recovery surface.
    expect(await screen.findByRole('button', { name: /retry/i })).toBeInTheDocument();
    expect(screen.queryByTestId('portfolio-cpm')).not.toBeInTheDocument();
  });
});
