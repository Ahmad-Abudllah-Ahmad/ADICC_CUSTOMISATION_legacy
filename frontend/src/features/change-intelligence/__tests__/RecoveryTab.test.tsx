// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Focused tests for the cost-recovery tab wiring added in W2: the
// recovery-performance index (#11, recovered vs entitled split by traceability)
// and the per-back-charge apportionment breakdown (#8). Mocks the feature api so
// no network happens; the page mounts straight on the cost-recovery tab.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/stores/useProjectContextStore', () => ({
  useProjectContextStore: (sel: (s: { activeProjectId: string }) => unknown) =>
    sel({ activeProjectId: 'p-1' }),
}));

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    getCoordinationPlan: vi.fn(),
    getCycleTimeBoard: vi.fn(),
    getCommsDigest: vi.fn(),
    getImpactProjection: vi.fn(),
    getRecoveryLedger: vi.fn(),
    listBackCharges: vi.fn(),
    getRecoveryPerformance: vi.fn(),
    getBackChargeApportionment: vi.fn(),
    apportionBackCharge: vi.fn(),
    clarifyChangeNote: vi.fn(),
    getDisputeRiskBoard: vi.fn(),
    getDecisionImpact: vi.fn(),
    getChangeWatch: vi.fn(),
  };
});

vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn().mockResolvedValue([]),
  apiPost: vi.fn(),
  getErrorMessage: (e: unknown) => String(e),
}));

import {
  getRecoveryLedger,
  listBackCharges,
  getRecoveryPerformance,
  getBackChargeApportionment,
  apportionBackCharge,
} from '../api';
import { ChangeIntelligencePage } from '../ChangeIntelligencePage';

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/change-intelligence']}>
        <ChangeIntelligencePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getRecoveryLedger).mockResolvedValue({
    project_id: 'p-1',
    item_count: 2,
    open_count: 1,
    primary_currency: 'USD',
    primary_outstanding: '500.00',
    by_party: [
      {
        party: 'subcontractor a',
        currency: 'USD',
        item_count: 2,
        open_count: 1,
        gross_total: '1700.00',
        chargeable_total: '1600.00',
        recovered_total: '1100.00',
        outstanding_total: '500.00',
      },
    ],
    by_currency: [
      { currency: 'USD', item_count: 2, chargeable_total: '1600.00', recovered_total: '1100.00', outstanding_total: '500.00' },
    ],
  });
  vi.mocked(listBackCharges).mockResolvedValue([
    {
      id: 'bc-1',
      project_id: 'p-1',
      source_ref: 'NCR-12',
      responsible_party: 'subcontractor a',
      description: 'Rework after defect',
      basis: 'NCR-12',
      gross_amount: '1000.00',
      chargeable_pct: '1.0000',
      chargeable_amount: '1000.00',
      currency: 'USD',
      status: 'agreed',
      recovered_amount: '0',
      outstanding: '1000.00',
      is_open: true,
      agreed_at: null,
      recovered_at: null,
    },
  ]);
  vi.mocked(getRecoveryPerformance).mockResolvedValue({
    project_id: 'p-1',
    item_count: 2,
    primary_currency: 'USD',
    primary_rate: '0.6900',
    by_currency: [
      {
        currency: 'USD',
        item_count: 2,
        chargeable_total: '1600.00',
        recovered_total: '1100.00',
        outstanding_total: '500.00',
        absorbed_total: '0.00',
        rate: '0.6900',
        by_cohort: [
          {
            cohort: 'high',
            currency: 'USD',
            item_count: 1,
            chargeable_total: '1000.00',
            recovered_total: '1000.00',
            outstanding_total: '0.00',
            absorbed_total: '0.00',
            rate: '1.0000',
          },
          {
            cohort: 'low',
            currency: 'USD',
            item_count: 1,
            chargeable_total: '600.00',
            recovered_total: '100.00',
            outstanding_total: '500.00',
            absorbed_total: '0.00',
            rate: '0.1667',
          },
        ],
        by_band: [],
      },
    ],
  });
  vi.mocked(getBackChargeApportionment).mockResolvedValue({
    back_charge_id: 'bc-1',
    project_id: 'p-1',
    currency: 'USD',
    chargeable_amount: '1000.00',
    share_total: '1000.00',
    is_apportioned: true,
    shares: [
      {
        id: 'ap-1',
        back_charge_id: 'bc-1',
        project_id: 'p-1',
        party: 'subcontractor a',
        basis: 'NCR-12',
        share_pct: '0.6000',
        share_amount: '600.00',
        currency: 'USD',
      },
      {
        id: 'ap-2',
        back_charge_id: 'bc-1',
        project_id: 'p-1',
        party: 'designer',
        basis: '',
        share_pct: '0.4000',
        share_amount: '400.00',
        currency: 'USD',
      },
    ],
  });
  vi.mocked(apportionBackCharge).mockResolvedValue({
    back_charge_id: 'bc-1',
    project_id: 'p-1',
    currency: 'USD',
    chargeable_amount: '1000.00',
    share_total: '1000.00',
    is_apportioned: true,
    shares: [],
  });
});

describe('RecoveryTab wiring (#8 + #11)', () => {
  it('shows the recovery-performance index with the high/low cohort split', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: /Cost recovery/i }));
    // The headline recovery rate (0.6900 -> 69%) renders.
    await waitFor(() => {
      expect(screen.getByText('69%')).toBeInTheDocument();
    });
    // The cohort table contrasts high (100%) against low (17%).
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByText('17%')).toBeInTheDocument();
    expect(getRecoveryPerformance).toHaveBeenCalledWith('p-1');
  });

  it('expands a back-charge to show its apportionment breakdown', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: /Cost recovery/i }));
    // The apportionment list shows the back-charge; expanding it fetches the
    // per-party split on demand.
    const toggle = await screen.findByText('Rework after defect');
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(getBackChargeApportionment).toHaveBeenCalledWith('p-1', 'bc-1');
    });
    // Both party shares render with their percentages.
    expect(await screen.findByText('designer')).toBeInTheDocument();
    expect(screen.getByText('60%')).toBeInTheDocument();
    expect(screen.getByText('40%')).toBeInTheDocument();
  });

  it('edits a back-charge apportionment and saves the new split', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: /Cost recovery/i }));
    fireEvent.click(await screen.findByText('Rework after defect'));

    // Open the apportionment editor; it seeds from the existing 60/40 split.
    fireEvent.click(await screen.findByRole('button', { name: /Edit split/i }));
    expect(await screen.findByText('Apportion back-charge')).toBeInTheDocument();

    // The seeded percentages are present and total 100, so save is enabled.
    expect(await screen.findByDisplayValue('60')).toBeInTheDocument();
    expect(screen.getByDisplayValue('40')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Save apportionment/i }));

    await waitFor(() => {
      expect(apportionBackCharge).toHaveBeenCalledWith('p-1', 'bc-1', [
        { party: 'subcontractor a', share_pct: '0.6' },
        { party: 'designer', share_pct: '0.4' },
      ]);
    });
  });
});
