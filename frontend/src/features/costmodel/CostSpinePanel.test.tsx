// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <CostSpinePanel>.
//
// Covers:
//   1. Renders the account-grouped grid from a mocked SpineRollup: each
//      control account appears as a group header above its own cost lines.
//   2. Surfaces the mixed-currency banner when mixed_currency is true, and
//      hides it (showing the project total) when it is false.

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { ControlAccount, CostLineRollup, SpineRollup } from './api';

/* ── i18n shim (interpolating defaultValue) ──────────────────────────────
 * Must export the full react-i18next surface (Trans / initReactI18next /
 * I18nextProvider) because the panel transitively imports app/i18n.ts via
 * the shared UI barrel. */

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

/* ── Toast mock (GenerateSpineButton reads it) ─────────────────────────── */

const toastMocks = vi.hoisted(() => ({ addToastMock: vi.fn() }));
vi.mock('@/stores/useToastStore', () => ({
  useToastStore: Object.assign(
    (selector: (s: { addToast: typeof toastMocks.addToastMock }) => unknown) =>
      selector({ addToast: toastMocks.addToastMock }),
    { getState: () => ({ addToast: toastMocks.addToastMock }) },
  ),
}));

/* ── API mock ──────────────────────────────────────────────────────────── */

const apiMocks = vi.hoisted(() => ({
  getSpineRollupMock: vi.fn(),
  generateSpineMock: vi.fn(),
  getLineRollupMock: vi.fn(),
}));
const getSpineRollupMock = apiMocks.getSpineRollupMock;
vi.mock('./api', () => ({
  costModelApi: {
    getSpineRollup: apiMocks.getSpineRollupMock,
    generateSpine: apiMocks.generateSpineMock,
    getLineRollup: apiMocks.getLineRollupMock,
  },
}));

import { CostSpinePanel } from './CostSpinePanel';

/* ── Fixtures ──────────────────────────────────────────────────────────── */

const accounts: ControlAccount[] = [
  {
    id: 'acc-1',
    project_id: 'proj-1',
    parent_id: null,
    code: '01',
    name: 'Substructure',
    classification_standard: 'din276',
    status: 'active',
    sort_order: 0,
  },
  {
    id: 'acc-2',
    project_id: 'proj-1',
    parent_id: null,
    code: '02',
    name: 'Superstructure',
    classification_standard: 'din276',
    status: 'active',
    sort_order: 1,
  },
];

function line(
  over: Partial<CostLineRollup> & Pick<CostLineRollup, 'cost_line_id' | 'code' | 'description'>,
): CostLineRollup {
  return {
    control_account_id: null,
    currency: 'EUR',
    estimate_amount: '1000.00',
    budget_planned: '900.00',
    budget_committed: '0.00',
    budget_actual: '0.00',
    po_committed: '500.00',
    contracted_value: '0.00',
    claimed_to_date: '250.00',
    variance_estimate_vs_budget: '100.00',
    links: {
      boq_position_ids: [],
      budget_line_ids: [],
      po_item_ids: [],
      contract_line_ids: [],
      rfq_ids: [],
    },
    ...over,
  };
}

const lines: CostLineRollup[] = [
  line({ cost_line_id: 'cl-1', code: '01.001', description: 'Excavation', control_account_id: 'acc-1' }),
  line({ cost_line_id: 'cl-2', code: '01.002', description: 'Foundations', control_account_id: 'acc-1' }),
  line({ cost_line_id: 'cl-3', code: '02.001', description: 'Columns', control_account_id: 'acc-2' }),
];

const totals: SpineRollup['totals'] = {
  estimate_amount: '3000.00',
  budget_planned: '2700.00',
  budget_committed: '0.00',
  budget_actual: '0.00',
  po_committed: '1500.00',
  contracted_value: '0.00',
  claimed_to_date: '750.00',
  variance_estimate_vs_budget: '300.00',
};

function rollup(over?: Partial<SpineRollup>): SpineRollup {
  return {
    currency: 'EUR',
    mixed_currency: false,
    accounts,
    lines,
    totals,
    ...over,
  };
}

afterEach(() => {
  cleanup();
  getSpineRollupMock.mockReset();
  toastMocks.addToastMock.mockReset();
});

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <CostSpinePanel projectId="proj-1" currency="EUR" />
    </QueryClientProvider>,
  );
}

describe('<CostSpinePanel>', () => {
  it('groups cost lines under their control account', async () => {
    getSpineRollupMock.mockResolvedValueOnce(rollup());
    renderPanel();

    // Account group headers render (each appears in the tree and as a grid
    // group header, so there are >= 2 matches; we only assert presence).
    await waitFor(() => expect(screen.getAllByText('Substructure').length).toBeGreaterThan(0));
    expect(screen.getAllByText('Superstructure').length).toBeGreaterThan(0);

    // The grid groups lines by account: locate each account's group header
    // ROW in the table and assert its lines follow it.
    const excavation = await screen.findByText('Excavation');
    const foundations = screen.getByText('Foundations');
    const columns = screen.getByText('Columns');
    expect(excavation).toBeInTheDocument();
    expect(foundations).toBeInTheDocument();
    expect(columns).toBeInTheDocument();

    // Grouping: the two substructure lines and the one superstructure line
    // are all present in the same table.
    const table = screen.getByRole('table');
    expect(within(table).getByText('Excavation')).toBeInTheDocument();
    expect(within(table).getByText('Columns')).toBeInTheDocument();
  });

  it('does NOT show the mixed-currency banner for a single-currency spine', async () => {
    getSpineRollupMock.mockResolvedValueOnce(rollup({ mixed_currency: false }));
    renderPanel();

    await waitFor(() => expect(screen.getByText('Excavation')).toBeInTheDocument());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    // Project total footer is shown when currencies are not mixed.
    expect(screen.getByText('Project total')).toBeInTheDocument();
  });

  it('shows the mixed-currency banner when mixed_currency is true', async () => {
    getSpineRollupMock.mockResolvedValueOnce(rollup({ mixed_currency: true }));
    renderPanel();

    await waitFor(() => expect(screen.getByText('Excavation')).toBeInTheDocument());
    const banner = screen.getByRole('alert');
    expect(banner).toBeInTheDocument();
    expect(banner.textContent).toMatch(/more than one currency/i);
    // Totals are meaningless across currencies, so the footer total is hidden.
    expect(screen.queryByText('Project total')).not.toBeInTheDocument();
  });
});
