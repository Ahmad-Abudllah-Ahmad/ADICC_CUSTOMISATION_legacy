// @ts-nocheck
/**
 * Smoke tests for the dependency (predecessor) editor (#348).
 *
 * Network is stubbed via ``vi.mock`` on the schedule ``./api`` module (the
 * editor calls ``scheduleApi.*``). React Query retries are disabled so the
 * empty relationships list surfaces immediately. We assert that picking a
 * predecessor + type + lag and clicking Add fires ``createRelationship`` with
 * the chosen values and then ``reschedule``, and that retyping / removing an
 * existing edge fires ``updateRelationship`` / ``deleteRelationship`` and
 * reschedules too.
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
      listRelationships: vi.fn(),
      createRelationship: vi.fn(),
      updateRelationship: vi.fn(),
      deleteRelationship: vi.fn(),
      reschedule: vi.fn(),
    },
  };
});

import { scheduleApi } from './api';
import { DependencyEditor } from './DependencyEditor';

const A = {
  id: 'a1',
  name: 'Foundation',
  start_date: '2024-01-01',
  end_date: '2024-01-05',
};
const B = {
  id: 'a2',
  name: 'Walls',
  start_date: '2024-01-08',
  end_date: '2024-01-12',
};
const C = {
  id: 'a3',
  name: 'Roof',
  start_date: '2024-01-15',
  end_date: '2024-01-20',
};
const ACTIVITIES = [A, B, C];

const EDGE = {
  id: 'r1',
  schedule_id: 's1',
  predecessor_id: 'a1',
  successor_id: 'a2',
  relationship_type: 'FS',
  lag_days: 0,
};

function renderEditor(successor = B) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DependencyEditor scheduleId="s1" activity={successor} activities={ACTIVITIES} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DependencyEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (scheduleApi.listRelationships as any).mockResolvedValue([]);
    (scheduleApi.createRelationship as any).mockResolvedValue({ id: 'r1' });
    (scheduleApi.updateRelationship as any).mockResolvedValue({ id: 'r1' });
    (scheduleApi.deleteRelationship as any).mockResolvedValue(undefined);
    (scheduleApi.reschedule as any).mockResolvedValue([]);
  });

  it('adds a predecessor with the chosen type + lag, then reschedules', async () => {
    renderEditor(B);
    expect(await screen.findByTestId('dependency-editor')).toBeInTheDocument();

    fireEvent.change(screen.getByTestId('dep-add-predecessor'), {
      target: { value: 'a1' },
    });
    fireEvent.change(screen.getByTestId('dep-add-type'), {
      target: { value: 'SS' },
    });
    fireEvent.change(screen.getByTestId('dep-add-lag'), {
      target: { value: '3' },
    });
    fireEvent.click(screen.getByTestId('dep-add-submit'));

    await waitFor(() => {
      expect(scheduleApi.createRelationship).toHaveBeenCalledWith('s1', {
        predecessor_id: 'a1',
        successor_id: 'a2',
        relationship_type: 'SS',
        lag_days: 3,
      });
    });
    await waitFor(() => expect(scheduleApi.reschedule).toHaveBeenCalledWith('s1'));
  });

  it('retypes an existing predecessor edge and reschedules', async () => {
    (scheduleApi.listRelationships as any).mockResolvedValue([EDGE]);
    renderEditor(B);

    const typeSelect = await screen.findByTestId('dep-type-r1');
    fireEvent.change(typeSelect, { target: { value: 'FF' } });

    await waitFor(() => {
      expect(scheduleApi.updateRelationship).toHaveBeenCalledWith('r1', {
        relationship_type: 'FF',
      });
    });
    await waitFor(() => expect(scheduleApi.reschedule).toHaveBeenCalledWith('s1'));
  });

  it('removes a predecessor edge and reschedules', async () => {
    (scheduleApi.listRelationships as any).mockResolvedValue([EDGE]);
    renderEditor(B);

    fireEvent.click(await screen.findByTestId('dep-remove-r1'));

    await waitFor(() => expect(scheduleApi.deleteRelationship).toHaveBeenCalledWith('r1'));
    await waitFor(() => expect(scheduleApi.reschedule).toHaveBeenCalledWith('s1'));
  });
});
