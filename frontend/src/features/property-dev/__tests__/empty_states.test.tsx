// @ts-nocheck
/**
 * UX polish wave — empty-state coverage for the Property-Development
 * dashboards.
 *
 * Asserts each dashboard widget renders a CTA-driven empty state (icon
 * + heading + description) when the backend returns a payload with no
 * rows, instead of falling back to a generic "no data" placeholder.
 * The dashboards-hub empty case must additionally surface a primary
 * action button that takes the user to the create-development flow.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
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
  getCashflowWaterfall,
  getInventoryAgeing,
  getFunnelConversion,
  getBuyerJourney,
} from '../api';

import { DashboardsHub } from '../dashboards/DashboardsHub';
import { InventoryHeatmap } from '../dashboards/InventoryHeatmap';
import { SalesVelocity } from '../dashboards/SalesVelocity';
import { CashFlowWaterfall } from '../dashboards/CashFlowWaterfall';
import { InventoryAgeing } from '../dashboards/InventoryAgeing';
import { FunnelConversion } from '../dashboards/FunnelConversion';
import { BuyerJourneyTimeline } from '../dashboards/BuyerJourneyTimeline';

/** Provider that gives React-Query consumers a fresh client per render
 *  with retries disabled so .mockResolvedValue() fires once per test. */
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

describe('property-dev empty states', () => {
  beforeEach(() => vi.clearAllMocks());

  it('DashboardsHub renders a CTA-driven empty state when no developments exist', async () => {
    (listDevelopments as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    renderWithProviders(<DashboardsHub />);
    expect(await screen.findByText(/No developments yet/i)).toBeInTheDocument();
    // CTA button to create the first development must be present.
    expect(
      await screen.findByRole('button', { name: /New Development/i }),
    ).toBeInTheDocument();
  });

  it('InventoryHeatmap renders a "no plots" empty state when total_units is 0', async () => {
    (getInventoryHeatmap as ReturnType<typeof vi.fn>).mockResolvedValue({
      development_id: 'dev-1',
      total_units: 0,
      status_counts: {},
      phases: [],
    });
    renderWithProviders(<InventoryHeatmap developmentId="dev-1" />);
    expect(await screen.findByText(/No plots yet/i)).toBeInTheDocument();
  });

  it('SalesVelocity renders a "no signed contracts" empty state', async () => {
    (getSalesVelocity as ReturnType<typeof vi.fn>).mockResolvedValue({
      development_id: 'dev-1',
      granularity: 'month',
      currencies: [],
      series: [],
      totals: { units: 0, area_m2: 0, revenue: [] },
    });
    renderWithProviders(<SalesVelocity developmentId="dev-1" />);
    expect(
      await screen.findByText(/No signed contracts yet/i),
    ).toBeInTheDocument();
  });

  it('CashFlowWaterfall renders an empty state when no series', async () => {
    (getCashflowWaterfall as ReturnType<typeof vi.fn>).mockResolvedValue({
      development_id: 'dev-1',
      series: [],
      currencies: [],
    });
    renderWithProviders(<CashFlowWaterfall developmentId="dev-1" />);
    expect(
      await screen.findByText(/No cash-flow data yet/i),
    ).toBeInTheDocument();
  });

  it('InventoryAgeing renders an "all sold" empty state when total_unsold is 0', async () => {
    (getInventoryAgeing as ReturnType<typeof vi.fn>).mockResolvedValue({
      development_id: 'dev-1',
      as_of: '2026-05-24',
      total_unsold: 0,
      buckets: [],
    });
    renderWithProviders(<InventoryAgeing developmentId="dev-1" />);
    expect(await screen.findByText(/All inventory sold/i)).toBeInTheDocument();
  });

  it('FunnelConversion renders an empty state when no leads in window', async () => {
    (getFunnelConversion as ReturnType<typeof vi.fn>).mockResolvedValue({
      development_id: 'dev-1',
      period_days: 90,
      stages: [],
      totals: { leads: 0, conversion_pct: 0 },
    });
    renderWithProviders(<FunnelConversion developmentId="dev-1" />);
    expect(
      await screen.findByText(/No leads in window/i),
    ).toBeInTheDocument();
  });

  it('BuyerJourneyTimeline renders an "no events" empty state for a fresh buyer', async () => {
    (getBuyerJourney as ReturnType<typeof vi.fn>).mockResolvedValue({
      buyer_id: 'b-1',
      full_name: 'Test Buyer',
      events: [],
      event_count: 0,
    });
    renderWithProviders(<BuyerJourneyTimeline buyerId="b-1" />);
    expect(await screen.findByText(/No events yet/i)).toBeInTheDocument();
  });
});
