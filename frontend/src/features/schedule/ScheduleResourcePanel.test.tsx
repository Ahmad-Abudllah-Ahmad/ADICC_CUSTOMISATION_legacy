// @ts-nocheck
/**
 * Smoke tests for the resource depth panel (T3.1).
 *
 * Network is stubbed via ``vi.mock`` on the schedule-advanced api module.
 * React Query retries are disabled so errors surface immediately. The panel has
 * two tabs: a resource histogram (resource picker + CSS demand bars) and a
 * leveling editor (resource limits -> preview -> apply). window.confirm is
 * stubbed so the apply path runs deterministically.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/features/schedule-advanced/api', () => ({
  listResources: vi.fn(),
  resourceHistogram: vi.fn(),
  levelPreview: vi.fn(),
  levelApply: vi.fn(),
}));

import {
  listResources,
  resourceHistogram,
  levelPreview,
  levelApply,
} from '@/features/schedule-advanced/api';
import { ScheduleResourcePanel } from './ScheduleResourcePanel';

const RESOURCES = [
  {
    id: 'r1',
    code: 'CREW-A',
    name: 'Crew A',
    resource_type: 'labor',
    home_project_id: null,
    default_cost_rate: '50',
    currency: 'EUR',
    capacity_percent: 100,
    status: 'active',
  },
];

const HISTOGRAM = {
  resource_id: 'r1',
  bucket: 'week',
  capacity_units: 4,
  peak_demand: 6,
  over_allocated_buckets: 1,
  cells: [
    {
      bucket_index: 0,
      start: '2026-01-05T00:00:00Z',
      end: '2026-01-12T00:00:00Z',
      label: 'Wk 1',
      demand_units: 6,
      demand_cost: '2400',
      available: 4,
      capacity_unknown: false,
      over_allocated: true,
      bookings: [],
    },
    {
      bucket_index: 1,
      start: '2026-01-12T00:00:00Z',
      end: '2026-01-19T00:00:00Z',
      label: 'Wk 2',
      demand_units: 2,
      demand_cost: '800',
      available: 4,
      capacity_unknown: false,
      over_allocated: false,
      bookings: [],
    },
  ],
};

const PREVIEW = {
  schedule_id: 's1',
  num_shifted: 1,
  finish_delta_days: 3,
  base_finish_workday: 40,
  leveled_finish_workday: 43,
  shifts: [{ activity_id: 'a1', base_es: 5, new_es: 8, delta: 3 }],
  segments: [],
  unresolvable: [{ activity_id: 'a2', resource: 'Crew A', required: 6, limit: 4 }],
  peak_before: { 'Crew A': 6 },
  peak_after: { 'Crew A': 4 },
};

const APPLY = {
  schedule_id: 's1',
  num_shifted: 1,
  num_applied: 1,
  num_skipped: 0,
  finish_delta_days: 3,
  base_finish_workday: 40,
  leveled_finish_workday: 43,
};

const NAMES = { a1: 'Foundation', a2: 'Structure' };

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ScheduleResourcePanel scheduleId="s1" projectId="p1" activitiesById={NAMES} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ScheduleResourcePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('renders the heading and both tab controls', async () => {
    (listResources as any).mockResolvedValue(RESOURCES);
    (resourceHistogram as any).mockResolvedValue(HISTOGRAM);
    renderPanel();

    expect(await screen.findByTestId('schedule-resource-panel')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /resource histogram/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /leveling/i })).toBeInTheDocument();
  });

  it('loads and renders the resource histogram bars on the first tab', async () => {
    (listResources as any).mockResolvedValue(RESOURCES);
    (resourceHistogram as any).mockResolvedValue(HISTOGRAM);
    renderPanel();

    const chart = await screen.findByTestId('resource-histogram');
    expect(chart).toBeInTheDocument();
    // Both buckets render as bars.
    const bars = await screen.findByTestId('resource-histogram-bars');
    expect(bars.textContent).toMatch(/Wk 1/);
    expect(bars.textContent).toMatch(/Wk 2/);
    await waitFor(() => {
      expect(resourceHistogram).toHaveBeenCalledWith('r1', expect.objectContaining({ bucket: 'week' }));
    });
  });

  it('shows an empty state when there are no resources', async () => {
    (listResources as any).mockResolvedValue([]);
    renderPanel();

    expect(await screen.findByText(/No resources yet/i)).toBeInTheDocument();
    // The histogram call must not fire without a resource.
    expect(resourceHistogram).not.toHaveBeenCalled();
  });

  it('previews a leveling run from the limits editor', async () => {
    (listResources as any).mockResolvedValue(RESOURCES);
    (resourceHistogram as any).mockResolvedValue(HISTOGRAM);
    (levelPreview as any).mockResolvedValue(PREVIEW);
    renderPanel();

    // Switch to the leveling tab.
    fireEvent.click(screen.getByRole('button', { name: /leveling/i }));

    // Empty state until a preview is run.
    expect(await screen.findByText(/No preview yet/i)).toBeInTheDocument();

    // Fill one limit row (name + max), then Preview.
    const rows = await screen.findByTestId('resource-limit-rows');
    const nameInput = rows.querySelector('input[type="text"]') as HTMLInputElement;
    const maxInput = rows.querySelector('input[type="number"]') as HTMLInputElement;
    fireEvent.change(nameInput, { target: { value: 'Crew A' } });
    fireEvent.change(maxInput, { target: { value: '4' } });

    fireEvent.click(screen.getByRole('button', { name: /^preview$/i }));

    await waitFor(() => {
      expect(levelPreview).toHaveBeenCalledTimes(1);
    });
    expect(levelPreview).toHaveBeenCalledWith(
      's1',
      expect.objectContaining({ resource_limits: { 'Crew A': 4 } }),
    );

    // Preview result renders: shifts table + per-resource peak + unresolvable.
    const result = await screen.findByTestId('resource-level-preview');
    expect(result).toBeInTheDocument();
    expect(await screen.findByTestId('resource-shifts-table')).toBeInTheDocument();
    expect(screen.getByTestId('resource-peak-table').textContent).toMatch(/Crew A/);
    expect(screen.getByTestId('resource-unresolvable').textContent).toMatch(/Structure/);
  });

  it('applies a leveling run after confirmation', async () => {
    (listResources as any).mockResolvedValue(RESOURCES);
    (resourceHistogram as any).mockResolvedValue(HISTOGRAM);
    (levelApply as any).mockResolvedValue(APPLY);
    renderPanel();

    fireEvent.click(screen.getByRole('button', { name: /leveling/i }));

    const rows = await screen.findByTestId('resource-limit-rows');
    const nameInput = rows.querySelector('input[type="text"]') as HTMLInputElement;
    const maxInput = rows.querySelector('input[type="number"]') as HTMLInputElement;
    fireEvent.change(nameInput, { target: { value: 'Crew A' } });
    fireEvent.change(maxInput, { target: { value: '4' } });

    fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));

    await waitFor(() => {
      expect(levelApply).toHaveBeenCalledTimes(1);
    });
    expect(window.confirm).toHaveBeenCalled();
    // The applied result card surfaces the returned counts.
    expect(await screen.findByTestId('resource-level-applied')).toBeInTheDocument();
  });

  it('surfaces a recovery card when the resource list fails', async () => {
    (listResources as any).mockRejectedValue(new Error('boom'));
    renderPanel();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /retry|try again/i })).toBeInTheDocument();
    });
  });
});
