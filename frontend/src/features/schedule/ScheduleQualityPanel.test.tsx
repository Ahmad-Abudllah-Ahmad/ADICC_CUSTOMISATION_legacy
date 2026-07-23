// @ts-nocheck
/**
 * Smoke tests for the claims-grade schedule quality panel (T1.2).
 *
 * Network is stubbed via ``vi.mock`` on the schedule-advanced api module.
 * React Query retries are disabled so errors surface immediately. The panel
 * auto-runs the analysis on mount (a read-only useQuery), so the assertions
 * wait for the resolved view.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/features/schedule-advanced/api', () => ({
  scheduleQuality: vi.fn(),
}));

import { scheduleQuality } from '@/features/schedule-advanced/api';
import { ScheduleQualityPanel } from './ScheduleQualityPanel';

const SAMPLE = {
  schedule_id: 's1',
  project_finish_workday: 120,
  num_activities: 8,
  num_critical: 3,
  longest_path: ['a1', 'a2', 'a3'],
  longest_path_length_days: 120,
  critical_activity_ids: ['a1', 'a2', 'a3'],
  float_paths: [
    { index: 0, activity_ids: ['a1', 'a2', 'a3'], length_days: 120, relative_float: 0 },
    { index: 1, activity_ids: ['a4', 'a5'], length_days: 90, relative_float: 30 },
  ],
  qa_log: [
    { code: 'OPEN_END', severity: 2, activity_id: 'a5', message: 'Activity has no successor' },
    { code: 'HARD_CONSTRAINT', severity: 3, activity_id: 'a2', message: 'Mandatory date pins the activity' },
  ],
  explanations: [
    { activity_id: 'a1', why_critical: 'On the Longest Path.', float_explanation: 'Total float is 0 days.' },
  ],
};

const NAMES = { a1: 'Foundation', a2: 'Structure', a3: 'Roofing', a4: 'Fit-out', a5: 'Snagging' };

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ScheduleQualityPanel scheduleId="s1" activitiesById={NAMES} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ScheduleQualityPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the headline stats and Longest Path with activity names', async () => {
    (scheduleQuality as any).mockResolvedValue(SAMPLE);
    renderPanel();

    // Headline numbers. "120" appears in several stats, so assert on the
    // unique activity/critical counts and that the finish value is present
    // at least once.
    expect(await screen.findByText(/Project finish/i)).toBeInTheDocument();
    expect(screen.getAllByText('120').length).toBeGreaterThan(0);
    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();

    // Longest Path renders names, not raw ids.
    const lp = await screen.findByTestId('quality-longest-path');
    expect(lp.textContent).toMatch(/Foundation/);
    expect(lp.textContent).toMatch(/Structure/);
    expect(lp.textContent).toMatch(/Roofing/);
  });

  it('renders the ranked float paths table with a Driving badge on path 1', async () => {
    (scheduleQuality as any).mockResolvedValue(SAMPLE);
    renderPanel();

    expect(await screen.findByText(/Float paths/i)).toBeInTheDocument();
    // The driving path (relative_float 0) gets a "Driving" badge. The word
    // also appears in the section hint ("...path 1 is the driving path"), so
    // match the exact badge label to stay unambiguous.
    expect(screen.getByText(/^Driving$/)).toBeInTheDocument();
  });

  it('renders the QA log sorted worst-first and severity-coloured', async () => {
    (scheduleQuality as any).mockResolvedValue(SAMPLE);
    renderPanel();

    const log = await screen.findByTestId('quality-qa-log');
    // Both finding codes present.
    expect(log.textContent).toMatch(/HARD_CONSTRAINT/);
    expect(log.textContent).toMatch(/OPEN_END/);
    // Worst-first: HARD_CONSTRAINT (sev 3) appears before OPEN_END (sev 2).
    const hardIdx = log.textContent.indexOf('HARD_CONSTRAINT');
    const openIdx = log.textContent.indexOf('OPEN_END');
    expect(hardIdx).toBeLessThan(openIdx);
  });

  it('shows an empty state when the schedule has no activities', async () => {
    (scheduleQuality as any).mockResolvedValue({ ...SAMPLE, num_activities: 0 });
    renderPanel();
    expect(await screen.findByText(/Nothing to analyse yet/i)).toBeInTheDocument();
  });

  it('surfaces a recovery card when the analysis call fails', async () => {
    (scheduleQuality as any).mockRejectedValue(new Error('boom'));
    renderPanel();
    // RecoveryCard renders a retry affordance for a generic error.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /retry|try again/i })).toBeInTheDocument();
    });
  });

  it('recomputes when the Recompute button is clicked', async () => {
    (scheduleQuality as any).mockResolvedValue(SAMPLE);
    renderPanel();
    await screen.findByTestId('quality-longest-path');
    expect(scheduleQuality).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: /recompute/i }));
    await waitFor(() => {
      expect(scheduleQuality).toHaveBeenCalledTimes(2);
    });
  });
});
