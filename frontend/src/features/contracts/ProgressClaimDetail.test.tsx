// @ts-nocheck
// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Component tests for the Gap I progress-claim bridge UI:
//   * ProgressClaimDetailPage — load/render, status-dependent buttons,
//     populate affordance only on editable claims.
//   * PopulatePreviewModal — preview render, select/deselect, empty state,
//     commit wiring.
//   * ProgressClaimLineTable — read-only vs editable rows, inline edit/save.
//
// The contracts API module is fully stubbed so no network is hit.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  render,
  screen,
  waitFor,
  fireEvent,
  within,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

// The global test setup (src/test/setup.ts) mocks react-router-dom with a
// useParams() that always returns {}, which would leave the detail page
// without a claimId and short-circuit its query. Restore the real router so
// the MemoryRouter/Route wrapper below actually supplies :claimId/:projectId.
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  );
  return { ...actual, useNavigate: () => vi.fn() };
});

// The global setup's i18n mock returns defaultValue but does not interpolate
// {{number}} / {{count}}. These components rely on standard i18next
// interpolation, so use an interpolation-aware t() here (matches the pattern
// used by the coordination feature tests).
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const defaultValue =
        opts && typeof opts === 'object' && 'defaultValue' in opts
          ? (opts.defaultValue as string)
          : key;
      if (!opts) return defaultValue;
      return defaultValue.replace(/\{\{(\w+)\}\}/g, (_, name) =>
        String(opts[name] ?? ''),
      );
    },
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
  Trans: ({ children }: { children: React.ReactNode }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
  I18nextProvider: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock('./api', () => ({
  getProgressClaim: vi.fn(),
  listClaimLines: vi.fn(),
  submitClaim: vi.fn(),
  approveClaim: vi.fn(),
  certifyClaim: vi.fn(),
  rejectClaim: vi.fn(),
  markClaimPaid: vi.fn(),
  populateClaimPreview: vi.fn(),
  commitClaimLines: vi.fn(),
  updateClaimLine: vi.fn(),
}));

vi.mock('@/stores/useToastStore', () => ({
  useToastStore: (sel) => sel({ addToast: vi.fn() }),
}));

vi.mock('@/stores/useAuthStore', () => ({
  useAuthStore: (sel) => sel({ userRole: 'manager' }),
}));

import * as api from './api';
import { ProgressClaimDetailPage } from './ProgressClaimDetailPage';
import { PopulatePreviewModal } from './PopulatePreviewModal';
import { ProgressClaimLineTable } from './ProgressClaimLineTable';

const CLAIM_ID = '00000000-0000-0000-0000-0000000000c1';
const PROJECT_ID = '00000000-0000-0000-0000-0000000000p1';

function claim(overrides = {}) {
  return {
    id: CLAIM_ID,
    contract_id: 'ctr-1',
    claim_number: 'PC-0001',
    period_start: '2026-05-01',
    period_end: '2026-05-31',
    claim_date: null,
    gross_amount: '400',
    retention_amount: '20',
    prior_claims_total: '0',
    net_due: '380',
    status: 'draft',
    submitted_at: null,
    approved_at: null,
    paid_at: null,
    currency: 'USD',
    metadata: {},
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-01T00:00:00Z',
    ...overrides,
  };
}

function previewItem(overrides = {}) {
  return {
    contract_line_id: 'line-1',
    contract_line_code: 'L1',
    contract_line_description: 'Concrete',
    boq_position_id: 'pos-1',
    unit: 'm3',
    contract_quantity: '10',
    contract_line_value: '1000',
    observed_pct: '40',
    period_label: '2026-W22',
    recorded_at: '2026-05-30T00:00:00Z',
    period_completed_qty: '4',
    period_completed_value: '400',
    cumulative_completed_value: '400',
    ...overrides,
  };
}

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/projects/${PROJECT_ID}/contracts/claims/${CLAIM_ID}`]}>
        <Routes>
          <Route
            path="/projects/:projectId/contracts/claims/:claimId"
            element={<ProgressClaimDetailPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderModal(props = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PopulatePreviewModal
          claimId={CLAIM_ID}
          currency="USD"
          onClose={vi.fn()}
          {...props}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ProgressClaimDetailPage', () => {
  it('loads and renders the claim header + totals', async () => {
    api.getProgressClaim.mockResolvedValue(claim());
    api.listClaimLines.mockResolvedValue([]);
    renderDetail();
    // The claim number renders in both the breadcrumb and the heading, so
    // assert on at least one match rather than a unique element.
    await waitFor(() => expect(screen.getAllByText(/PC-0001/).length).toBeGreaterThan(0));
    expect(screen.getByTestId('progress-claim-detail')).toBeTruthy();
  });

  it('shows the Populate button on a draft claim', async () => {
    api.getProgressClaim.mockResolvedValue(claim({ status: 'draft' }));
    api.listClaimLines.mockResolvedValue([]);
    renderDetail();
    await waitFor(() => expect(screen.getByTestId('populate-button')).toBeTruthy());
  });

  it('hides the Populate button on a certified claim', async () => {
    api.getProgressClaim.mockResolvedValue(claim({ status: 'certified' }));
    api.listClaimLines.mockResolvedValue([]);
    renderDetail();
    await waitFor(() => expect(screen.getAllByText(/PC-0001/).length).toBeGreaterThan(0));
    expect(screen.queryByTestId('populate-button')).toBeNull();
  });

  it('shows Submit on draft and Approve/Reject on submitted', async () => {
    api.getProgressClaim.mockResolvedValue(claim({ status: 'submitted' }));
    api.listClaimLines.mockResolvedValue([]);
    renderDetail();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Approve/i })).toBeTruthy(),
    );
    expect(screen.getByRole('button', { name: /Reject/i })).toBeTruthy();
    expect(screen.queryByText(/^Submit$/i)).toBeNull();
  });

  it('opens the populate modal when the button is clicked', async () => {
    api.getProgressClaim.mockResolvedValue(claim({ status: 'draft' }));
    api.listClaimLines.mockResolvedValue([]);
    api.populateClaimPreview.mockResolvedValue({
      claim_id: CLAIM_ID,
      contract_id: 'ctr-1',
      currency: 'USD',
      items: [previewItem()],
      skipped_unlinked: 0,
      skipped_no_progress: 0,
      skipped_foreign_currency: 0,
      gross: '400',
      retention: '20',
      prior_claims_total: '0',
      net_due: '380',
    });
    renderDetail();
    await waitFor(() => expect(screen.getByTestId('populate-button')).toBeTruthy());
    fireEvent.click(screen.getByTestId('populate-button'));
    await waitFor(() =>
      expect(screen.getByTestId('populate-preview-table')).toBeTruthy(),
    );
  });
});

describe('PopulatePreviewModal', () => {
  it('renders preview items with checkboxes and a selected summary', async () => {
    api.populateClaimPreview.mockResolvedValue({
      claim_id: CLAIM_ID,
      contract_id: 'ctr-1',
      currency: 'USD',
      items: [previewItem(), previewItem({ contract_line_id: 'line-2', contract_line_code: 'L2' })],
      skipped_unlinked: 0,
      skipped_no_progress: 0,
      skipped_foreign_currency: 0,
      gross: '800',
      retention: '40',
      prior_claims_total: '0',
      net_due: '760',
    });
    renderModal();
    await waitFor(() => expect(screen.getByTestId('populate-preview-table')).toBeTruthy());
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes.length).toBe(2);
    expect(screen.getByTestId('populate-selected-summary').textContent).toMatch(/2 selected/);
  });

  it('deselecting a row drops it from the selected count', async () => {
    api.populateClaimPreview.mockResolvedValue({
      claim_id: CLAIM_ID,
      contract_id: 'ctr-1',
      currency: 'USD',
      items: [previewItem(), previewItem({ contract_line_id: 'line-2' })],
      skipped_unlinked: 0,
      skipped_no_progress: 0,
      skipped_foreign_currency: 0,
      gross: '800',
      retention: '40',
      prior_claims_total: '0',
      net_due: '760',
    });
    renderModal();
    await waitFor(() => expect(screen.getByTestId('populate-preview-table')).toBeTruthy());
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    expect(screen.getByTestId('populate-selected-summary').textContent).toMatch(/1 selected/);
  });

  it('shows the empty alert and disables Commit when no items', async () => {
    api.populateClaimPreview.mockResolvedValue({
      claim_id: CLAIM_ID,
      contract_id: 'ctr-1',
      currency: 'USD',
      items: [],
      skipped_unlinked: 2,
      skipped_no_progress: 0,
      skipped_foreign_currency: 0,
      gross: '0',
      retention: '0',
      prior_claims_total: '0',
      net_due: '0',
    });
    renderModal();
    await waitFor(() => expect(screen.getByTestId('populate-empty')).toBeTruthy());
    const commit = screen.getByText(/Commit lines/i).closest('button');
    expect(commit?.disabled).toBe(true);
  });

  it('commits the selected lines and closes', async () => {
    const onClose = vi.fn();
    const onCommitted = vi.fn();
    api.populateClaimPreview.mockResolvedValue({
      claim_id: CLAIM_ID,
      contract_id: 'ctr-1',
      currency: 'USD',
      items: [previewItem()],
      skipped_unlinked: 0,
      skipped_no_progress: 0,
      skipped_foreign_currency: 0,
      gross: '400',
      retention: '20',
      prior_claims_total: '0',
      net_due: '380',
    });
    api.commitClaimLines.mockResolvedValue(claim());
    renderModal({ onClose, onCommitted });
    await waitFor(() => expect(screen.getByTestId('populate-preview-table')).toBeTruthy());
    fireEvent.click(screen.getByText(/Commit lines/i));
    await waitFor(() => expect(api.commitClaimLines).toHaveBeenCalledTimes(1));
    expect(api.commitClaimLines).toHaveBeenCalledWith(CLAIM_ID, [
      { contract_line_id: 'line-1', period_completed_pct: 40, period_completed_value: 400 },
    ]);
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});

describe('ProgressClaimLineTable', () => {
  const line = {
    id: 'cl-1',
    progress_claim_id: CLAIM_ID,
    contract_line_id: 'line-1',
    period_completed_qty: '4',
    period_completed_value: '400',
    period_completed_pct: '40',
    cumulative_completed_value: '400',
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-01T00:00:00Z',
  };

  function renderTable(editable) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={client}>
        <ProgressClaimLineTable
          claimId={CLAIM_ID}
          lines={[line]}
          currency="USD"
          editable={editable}
        />
      </QueryClientProvider>,
    );
  }

  it('is read-only when the claim is not editable (no Edit button)', () => {
    renderTable(false);
    expect(screen.queryByText(/^Edit$/i)).toBeNull();
  });

  it('exposes an inline edit → save flow when editable', async () => {
    api.updateClaimLine.mockResolvedValue(line);
    renderTable(true);
    fireEvent.click(screen.getByText(/^Edit$/i));
    const row = within(screen.getByTestId('claim-line-table'));
    const pctInput = row.getByLabelText(/% complete/i);
    fireEvent.change(pctInput, { target: { value: '55' } });
    fireEvent.click(screen.getByText(/^Save$/i));
    await waitFor(() => expect(api.updateClaimLine).toHaveBeenCalledTimes(1));
    expect(api.updateClaimLine).toHaveBeenCalledWith(
      'cl-1',
      expect.objectContaining({ period_completed_pct: 55 }),
    );
  });
});
