// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
// Tests for <RomReconciliationPanel>.
//
// Covers the read-side reconciliation of the project's conceptual baseline
// against the live detailed BOQ total:
//   1. An 'over' payload renders the traffic-light band, the signed variance
//      amount / percent, and the BOQ count - money verbatim from the API strings.
//   2. A 'no_baseline' payload degrades gracefully (no variance, "Not set").

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

/* ── i18n shim with interpolation ────────────────────────────────────────── */
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string } & Record<string, unknown>) => {
      if (typeof opts === 'object' && opts && 'defaultValue' in opts) {
        let dv = opts.defaultValue ?? '';
        for (const [k, v] of Object.entries(opts)) {
          if (k === 'defaultValue') continue;
          dv = dv.replaceAll(`{{${k}}}`, String(v));
        }
        return dv;
      }
      return _key;
    },
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
  Trans: ({ children }: { children: React.ReactNode }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
  I18nextProvider: ({ children }: { children: React.ReactNode }) => children,
}));

/* ── Active project + API mocks ──────────────────────────────────────────── */
vi.mock('@/shared/hooks/useActiveProjectId', () => ({ useActiveProjectId: () => 'proj-1' }));

const apiMocks = vi.hoisted(() => ({ reconciliationMock: vi.fn() }));
vi.mock('./api', () => ({
  romEstimateApi: {
    reconciliation: apiMocks.reconciliationMock,
    // The panel only calls reconciliation; the rest of the module surface is
    // stubbed so importing it (which also loads the page) never touches a
    // missing function.
    reference: vi.fn(),
    generate: vi.fn(),
    create: vi.fn(),
    list: vi.fn(),
    delete: vi.fn(),
    createBoq: vi.fn(),
  },
}));

import { RomReconciliationPanel } from './RomEstimatePage';

const OVER = {
  project_id: 'proj-1',
  status: 'over' as const,
  conceptual_total: '1000000',
  detailed_total: '1200000',
  variance_amount: '200000',
  variance_pct: '20.00',
  tolerance_pct: '10',
  currency: 'EUR',
  conceptual_currency: 'EUR',
  currency_mismatch: false,
  boq_count: 3,
  conceptual_estimate_id: 'est-1',
  conceptual_name: 'Concept A',
  conceptual_created_at: null,
};

const NO_BASELINE = {
  project_id: 'proj-1',
  status: 'no_baseline' as const,
  conceptual_total: null,
  detailed_total: '500000',
  variance_amount: null,
  variance_pct: null,
  tolerance_pct: '10',
  currency: 'EUR',
  conceptual_currency: '',
  currency_mismatch: false,
  boq_count: 2,
  conceptual_estimate_id: null,
  conceptual_name: '',
  conceptual_created_at: null,
};

afterEach(() => {
  cleanup();
  apiMocks.reconciliationMock.mockReset();
});

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RomReconciliationPanel />
    </QueryClientProvider>,
  );
}

describe('<RomReconciliationPanel>', () => {
  it('renders the over-budget band, signed variance and BOQ count', async () => {
    apiMocks.reconciliationMock.mockResolvedValueOnce(OVER);
    renderPanel();

    expect(await screen.findByText('Over concept')).toBeInTheDocument();
    expect(screen.getByText(/running above/i)).toBeInTheDocument();
    // Percent comes straight from the API string, with an explicit + sign.
    expect(screen.getByText('+20%')).toBeInTheDocument();
    // The saved baseline's name and the BOQ count are surfaced for context.
    expect(screen.getByText('Concept A')).toBeInTheDocument();
    expect(screen.getByText('3 bill(s) of quantities')).toBeInTheDocument();
  });

  it('degrades gracefully with no saved conceptual baseline', async () => {
    apiMocks.reconciliationMock.mockResolvedValueOnce(NO_BASELINE);
    renderPanel();

    expect(await screen.findByText('No baseline')).toBeInTheDocument();
    expect(screen.getByText(/No conceptual baseline/i)).toBeInTheDocument();
    // Both the conceptual value and the variance read "Not set".
    expect(screen.getAllByText('Not set')).toHaveLength(2);
  });
});
