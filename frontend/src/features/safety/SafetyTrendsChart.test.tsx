// @ts-nocheck
/**
 * Item 13 — SafetyTrendsChart tests.
 *
 *   1. Renders rolling KPIs + trend chip + chart container with data.
 *   2. Empty entries -> "No data available" empty state.
 *   3. Loading state renders the skeleton (query left pending).
 *   4. Period toggle re-queries with the new period.
 *
 * Network is stubbed via `vi.mock('@/shared/lib/api', …)`. Recharts inner
 * SVG does not lay out under jsdom (0px container), so assertions target the
 * surrounding DOM (testids, rolling figures, state text), not chart paths.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn(),
}));

import { apiGet } from '@/shared/lib/api';
import { SafetyTrendsChart } from './SafetyTrendsChart';

function renderChart(props = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SafetyTrendsChart projectId="proj-1" {...props} />
    </QueryClientProvider>,
  );
}

const sampleResponse = {
  period_type: 'monthly',
  entries: [
    {
      period: '2025-12',
      incident_count: 2,
      observation_count: 1,
      days_lost: 4,
      ltifr: 50.0,
      trir: 10.0,
      man_hours_total: 40000,
      recordable_incidents: 2,
      lost_time_incidents: 2,
    },
    {
      period: '2026-01',
      incident_count: 1,
      observation_count: 0,
      days_lost: 1,
      ltifr: 20.0,
      trir: 4.0,
      man_hours_total: 50000,
      recordable_incidents: 1,
      lost_time_incidents: 1,
    },
  ],
  rolling_12_month_ltifr: 35.0,
  rolling_12_month_trir: 7.0,
  current_period_ltifr: 20.0,
  current_period_trir: 4.0,
  trend_direction: 'improving',
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('SafetyTrendsChart', () => {
  it('renders rolling KPIs, trend chip, and chart with data', async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValue(sampleResponse);
    renderChart();

    await waitFor(() => {
      expect(screen.getByTestId('safety-trends-chart')).toBeTruthy();
    });
    expect(screen.getByTestId('rolling-ltifr').textContent).toContain('35');
    expect(screen.getByTestId('rolling-trir').textContent).toContain('7');
    expect(screen.getByTestId('safety-trend-direction').textContent).toMatch(/Improving/i);
  });

  it('shows the empty state when there are no entries', async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...sampleResponse,
      entries: [],
      rolling_12_month_ltifr: null,
      rolling_12_month_trir: null,
      trend_direction: 'unknown',
    });
    renderChart();

    await waitFor(() => {
      expect(screen.getByText(/No data available/i)).toBeTruthy();
    });
    expect(screen.queryByTestId('safety-trends-chart')).toBeNull();
  });

  it('shows a loading skeleton while the query is pending', () => {
    (apiGet as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    renderChart();
    // SkeletonTable renders while the query is pending; chart is absent.
    expect(screen.getByTestId('skeleton-table')).toBeTruthy();
    expect(screen.queryByTestId('safety-trends-chart')).toBeNull();
  });

  it('re-queries when the period toggle is switched to weekly', async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValue(sampleResponse);
    renderChart();

    await waitFor(() => {
      expect(screen.getByTestId('safety-trends-chart')).toBeTruthy();
    });

    const weeklyBtn = screen.getByRole('button', { name: /Weekly/i });
    fireEvent.click(weeklyBtn);

    await waitFor(() => {
      const calledWeekly = (apiGet as ReturnType<typeof vi.fn>).mock.calls.some(
        ([url]) => typeof url === 'string' && url.includes('period=weekly'),
      );
      expect(calledWeekly).toBe(true);
    });
  });
});
