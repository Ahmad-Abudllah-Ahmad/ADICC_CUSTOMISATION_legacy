// @ts-nocheck
/**
 * Item 13 — SafetyThresholdWidget tests.
 *
 *   1. Green status: current at/below baseline -> "Safe" badge.
 *   2. Red status: current well above baseline -> "Alert" badge.
 *   3. Unknown status (no man-hours) -> "No data", em-dash for the rate.
 *   4. Expand toggle reveals the delta detail + fetches the sparkline series.
 *
 * Network is stubbed via `vi.mock('@/shared/lib/api', …)`.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn(),
}));

import { apiGet } from '@/shared/lib/api';
import { SafetyThresholdWidget } from './SafetyThresholdWidget';

function renderWidget() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SafetyThresholdWidget projectId="proj-1" />
    </QueryClientProvider>,
  );
}

const greenAlert = {
  current_ltifr: 2.0,
  current_trir: 0.4,
  baseline_ltifr: 2.5,
  baseline_trir: 3.0,
  ltifr_delta: -0.5,
  trir_delta: -2.6,
  ltifr_status: 'green',
  trir_status: 'green',
  message: 'Safety rates are within baseline.',
};

const redAlert = {
  current_ltifr: 4.0,
  current_trir: 5.0,
  baseline_ltifr: 2.5,
  baseline_trir: 3.0,
  ltifr_delta: 1.5,
  trir_delta: 2.0,
  ltifr_status: 'red',
  trir_status: 'red',
  message: 'One or more safety rates exceed 150% of baseline - immediate action required.',
};

const unknownAlert = {
  current_ltifr: null,
  current_trir: null,
  baseline_ltifr: 2.5,
  baseline_trir: 3.0,
  ltifr_delta: null,
  trir_delta: null,
  ltifr_status: 'unknown',
  trir_status: 'unknown',
  message: 'Not enough man-hours data to compute frequency rates.',
};

const trendsResponse = {
  period_type: 'monthly',
  entries: [
    { period: '2025-11', ltifr: 5.0, trir: 1.0, incident_count: 1, observation_count: 0, days_lost: 0, man_hours_total: 200000, recordable_incidents: 1, lost_time_incidents: 1 },
    { period: '2025-12', ltifr: 3.0, trir: 0.6, incident_count: 1, observation_count: 0, days_lost: 0, man_hours_total: 333333, recordable_incidents: 1, lost_time_incidents: 1 },
    { period: '2026-01', ltifr: 2.0, trir: 0.4, incident_count: 1, observation_count: 0, days_lost: 0, man_hours_total: 500000, recordable_incidents: 1, lost_time_incidents: 1 },
  ],
  rolling_12_month_ltifr: 3.33,
  rolling_12_month_trir: 0.67,
  current_period_ltifr: 2.0,
  current_period_trir: 0.4,
  trend_direction: 'improving',
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('SafetyThresholdWidget', () => {
  it('renders a green Safe badge when rates are within baseline', async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValue(greenAlert);
    renderWidget();

    await waitFor(() => {
      expect(screen.getAllByText(/Safe/i).length).toBeGreaterThan(0);
    });
    // Both LTIFR and TRIR rows render.
    expect(screen.getByText('LTIFR')).toBeTruthy();
    expect(screen.getByText('TRIR')).toBeTruthy();
  });

  it('renders a red Alert badge when rates exceed 150% of baseline', async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValue(redAlert);
    renderWidget();

    await waitFor(() => {
      expect(screen.getAllByText(/Alert/i).length).toBeGreaterThan(0);
    });
  });

  it('shows No data and em-dash when rates are unknown', async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValue(unknownAlert);
    renderWidget();

    await waitFor(() => {
      expect(screen.getAllByText(/No data/i).length).toBeGreaterThan(0);
    });
    // The rate value renders the em-dash placeholder, never a fake 0.
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('expands to reveal delta detail and fetches the sparkline series', async () => {
    (apiGet as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(redAlert) // threshold-alert
      .mockResolvedValueOnce(trendsResponse); // sparkline trends
    renderWidget();

    await waitFor(() => {
      expect(screen.getByTestId('threshold-expand-toggle')).toBeTruthy();
    });

    fireEvent.click(screen.getByTestId('threshold-expand-toggle'));

    await waitFor(() => {
      expect(screen.getByText(/LTIFR delta/i)).toBeTruthy();
      expect(screen.getByText(/3-period LTIFR/i)).toBeTruthy();
    });
    // The expand triggered the trends fetch for the sparkline.
    const calledTrends = (apiGet as ReturnType<typeof vi.fn>).mock.calls.some(
      ([url]) => typeof url === 'string' && url.includes('/trends/extended/'),
    );
    expect(calledTrends).toBe(true);
  });
});
