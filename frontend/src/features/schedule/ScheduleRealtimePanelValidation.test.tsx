// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Guarded-edit error-distinction tests for the real-time collaboration panel
// (T3.4). These complement ScheduleRealtimePanel.test.tsx (presence, a
// successful guarded update, and the HTTP 409 stale-conflict recovery) by
// covering the two error branches that file leaves untested:
//
//   - HTTP 422 (validation): the panel must render the inline validation
//     message (data-testid="realtime-validation") and NOT the 409 conflict
//     surface and NOT an error toast - a malformed / non-editable field is a
//     user-fixable input problem, distinct from a lost-update conflict.
//   - any other error (e.g. 500): the panel must fall back to an error toast
//     and show neither the conflict surface nor the inline validation line.
//
// We also assert a successful retry after a 422 clears the inline message, so
// the distinction is end-to-end.
//
// The api module is automocked (no factory) so scheduleApi is fully stubbed;
// the real ApiError from the shared client is used so the panel's
// ``err.status`` branching runs for real. React Query retries are disabled.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import { ApiError } from '@/shared/lib/api';
import { useToastStore } from '@/stores/useToastStore';

vi.mock('./api');

import { scheduleApi } from './api';
import { ScheduleRealtimePanel } from './ScheduleRealtimePanel';

type AnyFn = ReturnType<typeof vi.fn>;

const ACTIVITIES = { a1: 'Foundation', a2: 'Structure' };
const PRESENCE = { schedule_id: 's1', users: [] };
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

/** Enter a valid progress value and click save, after the revision has loaded. */
async function submitProgress(value: string) {
  await waitFor(() => expect(screen.getByTestId('realtime-revision')).toHaveTextContent('4'));
  fireEvent.change(screen.getByLabelText(/New progress/i), { target: { value } });
  fireEvent.click(screen.getByRole('button', { name: /save change/i }));
}

describe('ScheduleRealtimePanel guarded-edit error distinction', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useToastStore.setState({ toasts: [], history: [] });
    (scheduleApi.getPresence as AnyFn).mockResolvedValue(PRESENCE);
    (scheduleApi.getActivityRevision as AnyFn).mockResolvedValue(REVISION);
  });

  it('renders the inline validation message on HTTP 422 (not a conflict, not a toast)', async () => {
    (scheduleApi.guardedUpdateActivity as AnyFn).mockRejectedValueOnce(
      new ApiError(422, 'Unprocessable Entity', {
        detail: 'progress_pct must be between 0 and 100',
      }),
    );
    renderPanel();
    await submitProgress('50');

    // Inline validation surface appears with the server's message.
    const inline = await screen.findByTestId('realtime-validation');
    expect(inline).toBeInTheDocument();
    expect(inline.textContent).toMatch(/progress_pct must be between 0 and 100/i);

    // It is NOT the 409 stale-conflict surface, and no error toast was raised.
    expect(screen.queryByTestId('realtime-conflict')).not.toBeInTheDocument();
    expect(useToastStore.getState().toasts).toHaveLength(0);
  });

  it('clears the inline validation message after a successful retry', async () => {
    (scheduleApi.guardedUpdateActivity as AnyFn)
      .mockRejectedValueOnce(
        new ApiError(422, 'Unprocessable Entity', {
          detail: 'progress_pct must be between 0 and 100',
        }),
      )
      .mockResolvedValueOnce({ activity: { id: 'a1', progress_pct: 50 }, revision: 5 });
    renderPanel();

    await submitProgress('50');
    expect(await screen.findByTestId('realtime-validation')).toBeInTheDocument();

    // Retry; the second call succeeds and the inline error clears.
    fireEvent.click(screen.getByRole('button', { name: /save change/i }));
    await waitFor(() => expect(scheduleApi.guardedUpdateActivity).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.queryByTestId('realtime-validation')).not.toBeInTheDocument(),
    );
    // The revision display advances to the server's new revision.
    expect(screen.getByTestId('realtime-revision')).toHaveTextContent('5');
  });

  it('falls back to an error toast on a non-409/422 failure (e.g. 500)', async () => {
    (scheduleApi.guardedUpdateActivity as AnyFn).mockRejectedValueOnce(
      new ApiError(500, 'Internal Server Error', { detail: 'Server exploded' }),
    );
    renderPanel();
    await submitProgress('50');

    // The error is surfaced via a toast (stored, not rendered here)...
    await waitFor(() => expect(useToastStore.getState().toasts.length).toBeGreaterThan(0));
    const toast = useToastStore.getState().toasts[0]!;
    expect(toast.type).toBe('error');

    // ...and neither the conflict surface nor the inline validation line shows.
    expect(screen.queryByTestId('realtime-conflict')).not.toBeInTheDocument();
    expect(screen.queryByTestId('realtime-validation')).not.toBeInTheDocument();
  });
});
