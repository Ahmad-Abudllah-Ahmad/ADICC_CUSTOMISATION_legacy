// @ts-nocheck
/**
 * UX polish wave — error-recovery coverage for the Property-Development
 * dashboards.
 *
 * Asserts that a thrown error from the underlying API surfaces as an
 * inline error card with a Retry button (NOT a blank screen / silent
 * failure / disappearing toast). Clicking Retry re-invokes the fetch,
 * and a subsequent success swaps the error UI for the chart content.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../api', () => ({
  listDevelopments: vi.fn(),
  getInventoryHeatmap: vi.fn(),
  getSalesVelocity: vi.fn(),
  getCashflowWaterfall: vi.fn(),
  getInventoryAgeing: vi.fn(),
  getFunnelConversion: vi.fn(),
  getBuyerJourney: vi.fn(),
}));

import {
  listDevelopments,
  getInventoryHeatmap,
  getSalesVelocity,
  getFunnelConversion,
  getBuyerJourney,
} from '../api';

import { DashboardsHub } from '../dashboards/DashboardsHub';
import { InventoryHeatmap } from '../dashboards/InventoryHeatmap';
import { SalesVelocity } from '../dashboards/SalesVelocity';
import { FunnelConversion } from '../dashboards/FunnelConversion';
import { BuyerJourneyTimeline } from '../dashboards/BuyerJourneyTimeline';

function renderWithProviders(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('property-dev error recovery', () => {
  beforeEach(() => vi.clearAllMocks());

  it('DashboardsHub: failed listDevelopments renders inline error card with Retry button', async () => {
    (listDevelopments as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Network unreachable'),
    );
    renderWithProviders(<DashboardsHub />);
    // Inline error card (NOT blank screen) must show the original message.
    await waitFor(() =>
      expect(
        screen.getByText(/Could not load developments/i),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/Network unreachable/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Retry/i }),
    ).toBeInTheDocument();
    // Status role surfaces this as an alert region for screen readers.
    expect(screen.getByTestId('dashboard-error')).toBeInTheDocument();
  });

  it('InventoryHeatmap: surfaces error with Retry, and Retry re-invokes fetch on success', async () => {
    const fn = getInventoryHeatmap as ReturnType<typeof vi.fn>;
    fn.mockRejectedValueOnce(new Error('Backend 500'));
    renderWithProviders(<InventoryHeatmap developmentId="dev-1" />);
    await waitFor(() =>
      expect(screen.getByText(/Backend 500/i)).toBeInTheDocument(),
    );
    expect(screen.getByTestId('dashboard-error-retry')).toBeInTheDocument();

    // Second call resolves to an empty heatmap; the click should clear
    // the error and the empty state should appear instead of the alert.
    fn.mockResolvedValueOnce({
      development_id: 'dev-1',
      total_units: 0,
      status_counts: {},
      phases: [],
    });
    fireEvent.click(screen.getByTestId('dashboard-error-retry'));
    await waitFor(() =>
      expect(screen.queryByText(/Backend 500/i)).not.toBeInTheDocument(),
    );
    expect(screen.getByText(/No plots yet/i)).toBeInTheDocument();
    // Fetch was called twice: initial render + Retry click.
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it('SalesVelocity: thrown error renders the error card (not a blank widget)', async () => {
    (getSalesVelocity as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Velocity API down'),
    );
    renderWithProviders(<SalesVelocity developmentId="dev-1" />);
    await waitFor(() =>
      expect(
        screen.getByText(/Could not load sales velocity/i),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/Velocity API down/i)).toBeInTheDocument();
    expect(screen.getByTestId('dashboard-error-retry')).toBeInTheDocument();
  });

  it('FunnelConversion: thrown error renders Retry-driven inline card', async () => {
    (getFunnelConversion as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Funnel API timeout'),
    );
    renderWithProviders(<FunnelConversion developmentId="dev-1" />);
    await waitFor(() =>
      expect(screen.getByText(/Funnel API timeout/i)).toBeInTheDocument(),
    );
    expect(screen.getByTestId('dashboard-error-retry')).toBeInTheDocument();
  });

  it('BuyerJourneyTimeline: thrown error surfaces Retry button (no blank screen)', async () => {
    (getBuyerJourney as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Journey 503'),
    );
    renderWithProviders(<BuyerJourneyTimeline buyerId="b-1" />);
    await waitFor(() =>
      expect(screen.getByText(/Journey 503/i)).toBeInTheDocument(),
    );
    expect(screen.getByTestId('dashboard-error-retry')).toBeInTheDocument();
  });
});
