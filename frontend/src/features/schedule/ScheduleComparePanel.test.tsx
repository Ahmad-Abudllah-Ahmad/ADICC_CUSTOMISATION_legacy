// @ts-nocheck
/**
 * Smoke tests for the schedule comparison / diff panel (T1.3).
 *
 * ``./api`` exports the ``scheduleApi`` object; we stub ``listBaselines`` and
 * ``diffSchedule`` on it while keeping the real types. The panel loads
 * baselines (a query) then runs the diff on demand (a mutation).
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return {
    ...actual,
    scheduleApi: {
      ...actual.scheduleApi,
      listBaselines: vi.fn(),
      diffSchedule: vi.fn(),
    },
  };
});

import { scheduleApi } from './api';
import { ScheduleComparePanel } from './ScheduleComparePanel';

const BASELINES = [
  {
    id: 'b1',
    schedule_id: 's1',
    project_id: 'p1',
    name: 'Contract baseline',
    baseline_date: '2026-01-01',
    snapshot_data: {},
    is_active: true,
    created_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'b2',
    schedule_id: 's1',
    project_id: 'p1',
    name: 'Revision 2',
    baseline_date: '2026-03-01',
    snapshot_data: {},
    is_active: false,
    created_by: null,
    created_at: '2026-03-01T00:00:00Z',
    updated_at: '2026-03-01T00:00:00Z',
  },
];

const DIFF = {
  schedule_id: 's1',
  base_label: 'Contract baseline',
  target_label: 'current',
  activities: [
    {
      key: 'a1',
      change_type: 'modified',
      categories: ['dates'],
      fields: { end_date: { from: '2026-02-01', to: '2026-02-08' } },
      finish_movement_days: 7,
      critical_path: true,
      name: 'Foundation',
      wbs_code: '1.1',
    },
    {
      key: 'a9',
      change_type: 'added',
      categories: ['scope'],
      fields: {},
      finish_movement_days: 0,
      critical_path: false,
      name: 'New inspection',
      wbs_code: '2.4',
    },
  ],
  relationships: [
    {
      key: ['a1', 'a2'],
      change_type: 'retyped',
      categories: ['logic'],
      fields: { relationship_type: { from: 'FS', to: 'SS' } },
    },
  ],
  calendars: [],
  summary: {
    net_finish_movement_days: 7,
    count_by_category: { dates: 1, scope: 1, logic: 1 },
    activities_added: 1,
    activities_removed: 0,
    activities_changed: 1,
    relationships_added: 0,
    relationships_removed: 0,
    relationships_retyped: 1,
    relationships_relagged: 0,
    critical_path_in: 1,
    critical_path_out: 0,
    cost_planned_delta: '25000.00',
    cost_actual_delta: '0',
    largest_slips: [{ key: 'a1', name: 'Foundation', finish_movement_days: 7 }],
  },
};

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ScheduleComparePanel
          scheduleId="s1"
          projectId="p1"
          currency="EUR"
          activitiesById={{ a1: 'Foundation', a2: 'Structure' }}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ScheduleComparePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows an empty state when the project has no baselines', async () => {
    (scheduleApi.listBaselines as any).mockResolvedValue([]);
    renderPanel();
    expect(await screen.findByText(/No baselines to compare/i)).toBeInTheDocument();
  });

  it('renders the base/target pickers and a pre-run empty state', async () => {
    (scheduleApi.listBaselines as any).mockResolvedValue(BASELINES);
    renderPanel();
    // Base defaults to the first baseline; target defaults to the live schedule.
    expect(await screen.findByLabelText(/Base \(from\)/i)).toBeInTheDocument();
    const target = screen.getByLabelText(/Target \(to\)/i) as HTMLSelectElement;
    expect(target.value).toBe('__live__');
    expect(screen.getByText(/No comparison run yet/i)).toBeInTheDocument();
  });

  it('runs the diff and renders the summary + change tables', async () => {
    (scheduleApi.listBaselines as any).mockResolvedValue(BASELINES);
    (scheduleApi.diffSchedule as any).mockResolvedValue(DIFF);
    renderPanel();

    await screen.findByLabelText(/Base \(from\)/i);
    fireEvent.click(screen.getByRole('button', { name: /^compare$/i }));

    await waitFor(() => expect(scheduleApi.diffSchedule).toHaveBeenCalledTimes(1));
    // Base baseline id is sent; target omitted (live).
    const [sid, body] = (scheduleApi.diffSchedule as any).mock.calls[0];
    expect(sid).toBe('s1');
    expect(body.base_baseline_id).toBe('b1');
    expect(body.target_baseline_id).toBeUndefined();

    // Summary roll-up + categorized tables render. "Foundation" appears in
    // both the activity table and the "Largest slips" list, so assert it is
    // present (>=1) and check the unique added-activity name too.
    expect(await screen.findByText(/Summary/i)).toBeInTheDocument();
    expect(screen.getByText(/Activity changes/i)).toBeInTheDocument();
    expect(screen.getAllByText('Foundation').length).toBeGreaterThan(0);
    expect(screen.getByText('New inspection')).toBeInTheDocument();
    expect(screen.getByText(/Relationship changes/i)).toBeInTheDocument();
  });

  it('sends target_baseline_id when a second baseline is chosen as target', async () => {
    (scheduleApi.listBaselines as any).mockResolvedValue(BASELINES);
    (scheduleApi.diffSchedule as any).mockResolvedValue(DIFF);
    renderPanel();

    const target = (await screen.findByLabelText(/Target \(to\)/i)) as HTMLSelectElement;
    fireEvent.change(target, { target: { value: 'b2' } });
    fireEvent.click(screen.getByRole('button', { name: /^compare$/i }));

    await waitFor(() => expect(scheduleApi.diffSchedule).toHaveBeenCalledTimes(1));
    const [, body] = (scheduleApi.diffSchedule as any).mock.calls[0];
    expect(body.base_baseline_id).toBe('b1');
    expect(body.target_baseline_id).toBe('b2');
  });
});
