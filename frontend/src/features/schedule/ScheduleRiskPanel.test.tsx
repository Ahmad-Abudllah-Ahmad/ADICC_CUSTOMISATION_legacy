// @ts-nocheck
/**
 * Smoke tests for the Monte-Carlo schedule risk panel (T2.1).
 *
 * The panel is run-on-demand (a mutation), so the tests click "Run simulation"
 * and assert on the resolved result. The schedule-advanced api module is
 * stubbed; the toast store is left real (it is inert in jsdom).
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/features/schedule-advanced/api', () => ({
  scheduleRisk: vi.fn(),
}));

import { scheduleRisk } from '@/features/schedule-advanced/api';
import { ScheduleRiskPanel } from './ScheduleRiskPanel';

const BASE_RESULT = {
  schedule_id: 's1',
  iterations: 2000,
  deterministic_finish: 100,
  mean: 108.4,
  std_dev: 6.2,
  cv_pct: 5.7,
  percentiles: { p5: 99, p10: 101, p25: 104, p50: 108, p75: 112, p80: 114, p90: 117, p95: 120 },
  contingency: 14,
  contingency_pct: 14,
  recommended_finish: 114,
  target_confidence: 80,
  prob_within_deterministic: 0.12,
  correlation: 0,
  seed: 42,
  convergence_status: 'converged',
  convergence_margin_pct: 0.3,
  histogram: [
    { bin_start: 98, bin_end: 102, count: 120 },
    { bin_start: 102, bin_end: 106, count: 340 },
    { bin_start: 106, bin_end: 110, count: 500 },
  ],
  cdf: [
    { x: 99, cumulative_prob: 0.05 },
    { x: 108, cumulative_prob: 0.5 },
    { x: 120, cumulative_prob: 0.95 },
  ],
  criticality: [
    { activity_id: 'a1', criticality_index: 0.92, cruciality: 0.4, duration_sensitivity: 0.55, mean_duration: 30 },
    { activity_id: 'a2', criticality_index: 0.71, cruciality: 0.3, duration_sensitivity: 0.4, mean_duration: 22 },
  ],
  drivers: [
    { activity_id: 'a1', rank_correlation: 0.6, swing_low: -4, swing_high: 7 },
    { activity_id: 'a2', rank_correlation: 0.4, swing_low: -2, swing_high: 3 },
  ],
  joint_confidence: null,
};

const NAMES = { a1: 'Foundation', a2: 'Structure' };

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ScheduleRiskPanel scheduleId="s1" activitiesById={NAMES} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ScheduleRiskPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the run form with sensible defaults and an empty state', () => {
    renderPanel();
    // Default iterations is 2000.
    expect((screen.getByLabelText(/Iterations/i) as HTMLInputElement).value).toBe('2000');
    expect((screen.getByLabelText(/Target confidence/i) as HTMLInputElement).value).toBe('80');
    expect(screen.getByText(/No simulation run yet/i)).toBeInTheDocument();
  });

  it('runs the simulation and renders the finish percentile chips', async () => {
    (scheduleRisk as any).mockResolvedValue(BASE_RESULT);
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: /run simulation/i }));

    await waitFor(() => expect(scheduleRisk).toHaveBeenCalledTimes(1));
    // P5 / P50 / P95 chips render the resolved percentile values.
    expect(await screen.findByText('P50')).toBeInTheDocument();
    expect(screen.getByText('108')).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();
    // Criticality table shows activity names.
    expect(screen.getByText('Foundation')).toBeInTheDocument();
  });

  it('passes the cost inputs only when the cost toggle is enabled with a base cost', async () => {
    (scheduleRisk as any).mockResolvedValue({
      ...BASE_RESULT,
      joint_confidence: {
        target_finish: 114,
        target_cost: 1_100_000,
        jcl: 0.62,
        prob_on_time: 0.8,
        prob_on_budget: 0.75,
        cost_mean: 1_050_000,
        cost_percentiles: { p50: 1_040_000, p80: 1_120_000 },
        correlation: 0,
        scatter: [
          { finish: 105, cost: 1_000_000 },
          { finish: 120, cost: 1_200_000 },
        ],
      },
    });
    renderPanel();

    // Enable cost + enter a base cost.
    fireEvent.click(screen.getByLabelText(/Add cost inputs/i));
    fireEvent.change(screen.getByLabelText(/Base cost/i), { target: { value: '1000000' } });
    fireEvent.click(screen.getByRole('button', { name: /run simulation/i }));

    await waitFor(() => expect(scheduleRisk).toHaveBeenCalledTimes(1));
    // The request body carries cost_inputs with the entered base cost.
    const [, body] = (scheduleRisk as any).mock.calls[0];
    expect(body.cost_inputs).toBeTruthy();
    expect(body.cost_inputs.base_cost).toBe(1_000_000);

    // The JCL block renders. "Joint Confidence Level" also appears in the
    // cost-toggle label, so assert on the block testid + a JCL-only chip.
    const jcl = await screen.findByTestId('risk-jcl');
    expect(jcl).toBeInTheDocument();
    expect(jcl.textContent).toMatch(/Joint Confidence Level/i);
    expect(jcl.textContent).toMatch(/on time/i);
    expect(jcl.textContent).toMatch(/on budget/i);
  });

  it('does not attach cost inputs when the toggle is off', async () => {
    (scheduleRisk as any).mockResolvedValue(BASE_RESULT);
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: /run simulation/i }));
    await waitFor(() => expect(scheduleRisk).toHaveBeenCalledTimes(1));
    const [, body] = (scheduleRisk as any).mock.calls[0];
    expect(body.cost_inputs).toBeUndefined();
    // Core run params flow through.
    expect(body.iterations).toBe(2000);
    expect(body.target_confidence).toBe(80);
  });
});
