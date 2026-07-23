// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Smoke tests for the Portfolio / multi-project page.
//
// Both API layers the page depends on are stubbed:
//   - ./portfolioCpmApi      (the portfolio tree + cross-project CPM)
//   - @/features/schedule/api (the active-project schedule list, used by the
//     cross-links panel)
//
// We verify:
//   - the portfolio tree renders its nodes,
//   - picking a node fetches and renders the cross-project CPM result (rolled-up
//     stats + the critical-path table).
//
// React Query runs with retry disabled so any error surfaces immediately.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

vi.mock('./portfolioCpmApi', () => ({
  portfolioCpmApi: {
    getTree: vi.fn(),
    createNode: vi.fn(),
    patchNode: vi.fn(),
    deleteNode: vi.fn(),
    attachProject: vi.fn(),
    detachProject: vi.fn(),
    createCrossLink: vi.fn(),
    listCrossLinks: vi.fn(),
    deleteCrossLink: vi.fn(),
    nodeCpm: vi.fn(),
  },
}));

vi.mock('@/features/schedule/api', () => ({
  scheduleApi: {
    listSchedules: vi.fn(),
    getGantt: vi.fn(),
  },
}));

import { portfolioCpmApi } from './portfolioCpmApi';
import { scheduleApi } from '@/features/schedule/api';
import { PortfolioPage } from './PortfolioPage';

const mockGetTree = portfolioCpmApi.getTree as ReturnType<typeof vi.fn>;
const mockNodeCpm = portfolioCpmApi.nodeCpm as ReturnType<typeof vi.fn>;
const mockListSchedules = scheduleApi.listSchedules as ReturnType<typeof vi.fn>;
const mockGetGantt = scheduleApi.getGantt as ReturnType<typeof vi.fn>;

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
    children: [
      {
        id: '22222222-2222-2222-2222-222222222222',
        parent_id: NODE_ID,
        node_type: 'programme',
        name: 'Bridges Programme',
        code: '',
        sort_order: 0,
        project_ids: ['p3'],
        children: [],
      },
    ],
  },
];

const sampleCpm = {
  node_id: NODE_ID,
  schedule_count: 2,
  activity_count: 5,
  project_finish_workday: 42,
  cross_links_applied: 1,
  cross_links_omitted: 0,
  critical_path: [
    {
      schedule_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      activity_id: 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
      es: 0,
      ef: 10,
      ls: 0,
      lf: 10,
      total_float: 0,
      is_critical: true,
    },
  ],
  activities: [
    {
      schedule_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      activity_id: 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
      es: 0,
      ef: 10,
      ls: 0,
      lf: 10,
      total_float: 0,
      is_critical: true,
    },
  ],
};

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

describe('PortfolioPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetTree.mockResolvedValue(sampleTree);
    mockNodeCpm.mockResolvedValue(sampleCpm);
    // No active project in the store by default, so the cross-links panel shows
    // its "pick a project" empty state and never calls the schedule API.
    mockListSchedules.mockResolvedValue([]);
    mockGetGantt.mockResolvedValue({ activities: [] });
  });

  it('renders the portfolio tree nodes', async () => {
    renderPage();
    const list = await screen.findByTestId('portfolio-tree-list');
    expect(within(list).getByText('North Region Portfolio')).toBeInTheDocument();
    expect(within(list).getByText('Bridges Programme')).toBeInTheDocument();
    // CPM is not fetched until a node is picked.
    expect(mockNodeCpm).not.toHaveBeenCalled();
  });

  it('shows a pick-a-node prompt before any node is selected', async () => {
    renderPage();
    await screen.findByTestId('portfolio-tree-list');
    expect(screen.getByText('Pick a node')).toBeInTheDocument();
  });

  it('runs and renders the cross-project CPM when a node is picked', async () => {
    renderPage();
    const list = await screen.findByTestId('portfolio-tree-list');
    fireEvent.click(within(list).getByText('North Region Portfolio'));

    // The CPM result panel renders with the rolled-up stats + critical path.
    await waitFor(() => expect(screen.getByTestId('portfolio-cpm')).toBeInTheDocument());
    expect(mockNodeCpm).toHaveBeenCalledWith(NODE_ID);

    // Finish work-day stat from the mocked result.
    expect(screen.getByText('42')).toBeInTheDocument();
    // The critical-path table is present with one row.
    expect(screen.getByTestId('portfolio-cp-table')).toBeInTheDocument();
  });
});
