// @ts-nocheck
/**
 * Smoke tests for the real-time collaboration panel (T3.4).
 *
 * ``./api`` exports the ``scheduleApi`` object; we stub ``getPresence``,
 * ``getActivityRevision`` and ``guardedUpdateActivity`` on it while keeping the
 * real types. The panel polls presence (a query), reads the selected activity's
 * revision (a query), then runs a guarded update (a mutation). A 409 from the
 * mutation must render the stale-conflict recovery instead of a toast; we throw
 * a real ``ApiError`` so the panel's ``err.status`` branch is exercised.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import { ApiError } from '@/shared/lib/api';

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return {
    ...actual,
    scheduleApi: {
      ...actual.scheduleApi,
      getPresence: vi.fn(),
      getActivityRevision: vi.fn(),
      guardedUpdateActivity: vi.fn(),
    },
  };
});

import { scheduleApi } from './api';
import { ScheduleRealtimePanel } from './ScheduleRealtimePanel';

const ACTIVITIES = { a1: 'Foundation', a2: 'Structure' };

const PRESENCE = {
  schedule_id: 's1',
  users: [
    { user_id: 'u1', user_name: 'Ada Lovelace' },
    { user_id: 'u2', user_name: 'Grace Hopper' },
  ],
};

const REVISION = { activity_id: 'a1', revision: 4 };

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ScheduleRealtimePanel scheduleId="s1" projectId="p1" activitiesById={ACTIVITIES} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ScheduleRealtimePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Sensible defaults; individual tests override as needed.
    (scheduleApi.getPresence as any).mockResolvedValue(PRESENCE);
    (scheduleApi.getActivityRevision as any).mockResolvedValue(REVISION);
  });

  it('renders the presence roster with connected co-editors', async () => {
    renderPanel();
    expect(await screen.findByText('Ada Lovelace')).toBeInTheDocument();
    expect(screen.getByText('Grace Hopper')).toBeInTheDocument();
    expect(scheduleApi.getPresence).toHaveBeenCalledWith('s1');
  });

  it('shows an empty roster state when no one else is present', async () => {
    (scheduleApi.getPresence as any).mockResolvedValue({ schedule_id: 's1', users: [] });
    renderPanel();
    expect(await screen.findByText(/No one else is here/i)).toBeInTheDocument();
  });

  it('runs a successful guarded update carrying the loaded base revision', async () => {
    (scheduleApi.guardedUpdateActivity as any).mockResolvedValue({
      activity: { id: 'a1', progress_pct: 50 },
      revision: 5,
    });
    renderPanel();

    // The current revision loads for the default activity (a1).
    await waitFor(() => expect(screen.getByTestId('realtime-revision')).toHaveTextContent('4'));

    // Enter a new progress value and save.
    fireEvent.change(screen.getByLabelText(/New progress/i), { target: { value: '50' } });
    fireEvent.click(screen.getByRole('button', { name: /save change/i }));

    await waitFor(() => expect(scheduleApi.guardedUpdateActivity).toHaveBeenCalledTimes(1));
    const [aid, baseRev, fields] = (scheduleApi.guardedUpdateActivity as any).mock.calls[0];
    expect(aid).toBe('a1');
    expect(baseRev).toBe(4); // the revision the client loaded
    expect(fields).toEqual({ progress_pct: 50 });

    // The revision display advances to the server's new revision.
    await waitFor(() => expect(screen.getByTestId('realtime-revision')).toHaveTextContent('5'));
  });

  it('renders the stale-conflict recovery on HTTP 409 and reloads on retry', async () => {
    (scheduleApi.guardedUpdateActivity as any).mockRejectedValueOnce(
      new ApiError(409, 'Conflict', {
        detail: 'Activity was modified by another user',
        current_revision: 7,
        current_state: { id: 'a1', progress_pct: 80 },
      }),
    );
    renderPanel();

    await waitFor(() => expect(screen.getByTestId('realtime-revision')).toHaveTextContent('4'));

    fireEvent.change(screen.getByLabelText(/New progress/i), { target: { value: '50' } });
    fireEvent.click(screen.getByRole('button', { name: /save change/i }));

    // The conflict surface appears (not a toast) and names the authoritative revision.
    expect(await screen.findByTestId('realtime-conflict')).toBeInTheDocument();
    expect(screen.getByText(/changed since you loaded it/i)).toBeInTheDocument();

    // Reloading re-reads the revision; serve the new authoritative value.
    (scheduleApi.getActivityRevision as any).mockResolvedValue({ activity_id: 'a1', revision: 7 });
    fireEvent.click(screen.getByRole('button', { name: /reload latest/i }));

    // After the reload the conflict clears and the base revision is the latest.
    await waitFor(() =>
      expect(screen.queryByTestId('realtime-conflict')).not.toBeInTheDocument(),
    );
    expect(screen.getByTestId('realtime-revision')).toHaveTextContent('7');
  });
});
