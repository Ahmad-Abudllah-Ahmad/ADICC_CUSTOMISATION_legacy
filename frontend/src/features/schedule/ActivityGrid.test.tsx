// @ts-nocheck
/**
 * Smoke tests for the editable activity grid (schedule "Table" view).
 *
 * Network is stubbed via ``vi.mock`` on the schedule ``./api`` module. We assert
 * that inline edits write through ``updateActivity`` with the right body: a name
 * edit sends just the name; a start edit shifts the end by the same number of
 * calendar days (moving the bar, preserving the span); an end edit sends just
 * the end; and an end that falls before the start is rejected client-side (no
 * PATCH). We also assert the Reschedule button calls ``reschedule`` and the
 * predecessors / add cells fire their callbacks so the parent can open the
 * shared dependency editor / add-activity modal.
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
      updateActivity: vi.fn(),
      reschedule: vi.fn(),
    },
  };
});

import { scheduleApi } from './api';
import { ActivityGrid } from './ActivityGrid';

const A = {
  id: 'a1',
  name: 'Foundation',
  wbs_code: '01',
  start_date: '2024-01-01',
  end_date: '2024-01-05',
  duration_days: 5,
  progress_pct: 0,
  activity_type: 'task',
  dependencies: [],
};
const B = {
  id: 'a2',
  name: 'Walls',
  wbs_code: '02',
  start_date: '2024-01-08',
  end_date: '2024-01-12',
  duration_days: 5,
  progress_pct: 40,
  activity_type: 'task',
  dependencies: [{ activity_id: 'a1', type: 'FS', lag_days: 0 }],
};
const ACTIVITIES = [A, B];

function renderGrid(props = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const merged = {
    scheduleId: 's1',
    activities: ACTIVITIES,
    onEditDependencies: vi.fn(),
    onAddActivity: vi.fn(),
    ...props,
  };
  const utils = render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ActivityGrid {...merged} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...utils, props: merged };
}

describe('ActivityGrid', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (scheduleApi.updateActivity as any).mockResolvedValue({ id: 'a1' });
    (scheduleApi.reschedule as any).mockResolvedValue([]);
  });

  it('renders one row per activity', () => {
    renderGrid();
    expect(screen.getByTestId('activity-grid')).toBeInTheDocument();
    expect(screen.getByTestId('grid-row-a1')).toBeInTheDocument();
    expect(screen.getByTestId('grid-row-a2')).toBeInTheDocument();
  });

  it('commits a name edit as just the name', async () => {
    renderGrid();
    const input = screen.getByTestId('grid-name-a1');
    fireEvent.change(input, { target: { value: 'Footings' } });
    fireEvent.blur(input);
    await waitFor(() =>
      expect(scheduleApi.updateActivity).toHaveBeenCalledWith('a1', { name: 'Footings' }),
    );
  });

  it('does not PATCH when a name is unchanged', () => {
    renderGrid();
    const input = screen.getByTestId('grid-name-a1');
    fireEvent.blur(input);
    expect(scheduleApi.updateActivity).not.toHaveBeenCalled();
  });

  it('shifts the end by the same delta when the start moves', async () => {
    renderGrid();
    const start = screen.getByTestId('grid-start-a1');
    // 2024-01-01 -> 2024-01-03 is +2 days, so the 2024-01-05 end becomes 2024-01-07.
    fireEvent.change(start, { target: { value: '2024-01-03' } });
    fireEvent.blur(start);
    await waitFor(() =>
      expect(scheduleApi.updateActivity).toHaveBeenCalledWith('a1', {
        start_date: '2024-01-03',
        end_date: '2024-01-07',
      }),
    );
  });

  it('commits an end edit as just the end', async () => {
    renderGrid();
    const end = screen.getByTestId('grid-end-a1');
    fireEvent.change(end, { target: { value: '2024-01-09' } });
    fireEvent.blur(end);
    await waitFor(() =>
      expect(scheduleApi.updateActivity).toHaveBeenCalledWith('a1', { end_date: '2024-01-09' }),
    );
  });

  it('rejects an end before the start without PATCHing', () => {
    renderGrid();
    const end = screen.getByTestId('grid-end-a1');
    fireEvent.change(end, { target: { value: '2023-12-30' } });
    fireEvent.blur(end);
    expect(scheduleApi.updateActivity).not.toHaveBeenCalled();
  });

  it('recomputes dates via reschedule', async () => {
    renderGrid();
    fireEvent.click(screen.getByTestId('grid-reschedule'));
    await waitFor(() => expect(scheduleApi.reschedule).toHaveBeenCalledWith('s1'));
  });

  it('opens the dependency editor for a row', () => {
    const { props } = renderGrid();
    fireEvent.click(screen.getByTestId('grid-deps-a1'));
    expect(props.onEditDependencies).toHaveBeenCalledWith('a1');
  });

  it('asks the parent to add an activity', () => {
    const { props } = renderGrid();
    fireEvent.click(screen.getByTestId('grid-add-activity'));
    expect(props.onAddActivity).toHaveBeenCalled();
  });
});
