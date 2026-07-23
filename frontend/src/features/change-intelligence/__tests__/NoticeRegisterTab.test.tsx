// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Focused tests for the contractual notice / time-bar register tab. Mocks the
// feature api so no network happens; the page mounts on the default tab and the
// test switches to the Time bar tab. Verifies the worst-first order, the
// traffic-light status chip, the signed countdown, the entitlement-at-risk flag
// when a required notice has no proof on file, and that the contract-standard
// filter is passed through to the endpoint.
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
    clarifyChangeNote: vi.fn(),
    getDisputeRiskBoard: vi.fn(),
    getDecisionImpact: vi.fn(),
    getChangeWatch: vi.fn(),
    getNoticeRegister: vi.fn(),
  };
});

vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn().mockResolvedValue([]),
  apiPost: vi.fn(),
  getErrorMessage: (e: unknown) => String(e),
}));

import { getNoticeRegister } from '../api';
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
  // A worst-first register: an overdue, entitlement-at-risk claim notice with no
  // proof on file, then a due-soon response clock, then an upcoming one.
  vi.mocked(getNoticeRegister).mockResolvedValue({
    project_id: 'p-1',
    contract_standard: 'FIDIC',
    generated_at: '2026-07-01T00:00:00Z',
    due_soon_days: 7,
    clocks: [
      {
        source_kind: 'variation_request',
        source_id: 'vr-7',
        source_ref: 'VR-7',
        title: 'Additional waterproofing to basement',
        standard: 'FIDIC',
        notice_type: 'claim_notice',
        clause_ref: 'FIDIC 20.1',
        trigger_date: '2026-05-20T00:00:00Z',
        period_days: 28,
        deadline: '2026-06-17T00:00:00Z',
        days_remaining: -5,
        status: 'overdue',
        requires_notice: true,
        proof_on_file: false,
        satisfied_at: null,
        served_late: false,
        entitlement_at_risk: true,
        is_open: true,
      },
      {
        source_kind: 'change_order',
        source_id: 'co-3',
        source_ref: 'CO-3',
        title: 'Revised slab detail',
        standard: 'FIDIC',
        notice_type: 'response',
        clause_ref: 'FIDIC 3.5',
        trigger_date: '2026-06-20T00:00:00Z',
        period_days: 28,
        deadline: '2026-07-05T00:00:00Z',
        days_remaining: 4,
        status: 'due_soon',
        requires_notice: false,
        proof_on_file: false,
        satisfied_at: null,
        served_late: false,
        entitlement_at_risk: false,
        is_open: true,
      },
      {
        source_kind: 'change_order',
        source_id: 'co-8',
        source_ref: 'CO-8',
        title: 'Extra sockets to office',
        standard: 'FIDIC',
        notice_type: 'response',
        clause_ref: 'FIDIC 3.5',
        trigger_date: '2026-06-28T00:00:00Z',
        period_days: 28,
        deadline: '2026-07-26T00:00:00Z',
        days_remaining: 20,
        status: 'upcoming',
        requires_notice: false,
        proof_on_file: false,
        satisfied_at: null,
        served_late: false,
        entitlement_at_risk: false,
        is_open: true,
      },
    ],
    summary: {
      total: 3,
      open_total: 3,
      counts_by_status: { overdue: 1, due_soon: 1, upcoming: 1, met: 0, unknown: 0 },
      at_risk: 1,
      proof_missing: 1,
      overdue: 1,
      due_soon: 1,
    },
  });
});

describe('NoticeRegisterTab (contractual notice / time-bar register)', () => {
  it('renders the register worst-first with status chip, countdown and summary', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: /Time bar/i }));

    // The overdue clock surfaces with its source record and clause reference.
    await waitFor(() => {
      expect(screen.getByText('VR-7')).toBeInTheDocument();
    });
    expect(screen.getByText('Clause FIDIC 20.1')).toBeInTheDocument();
    // The signed countdown reads the overdue days off the negative remainder.
    expect(screen.getByText('5d overdue')).toBeInTheDocument();
    // The at-risk summary tile rendered (exact text, distinct from the pill).
    expect(screen.getByText('At risk')).toBeInTheDocument();
    // The register is fetched with no standard override by default.
    expect(getNoticeRegister).toHaveBeenCalledWith('p-1', { standard: undefined });

    // Worst-first: the overdue VR-7 precedes the upcoming CO-8 in the document.
    const overdue = screen.getByText('VR-7');
    const upcoming = screen.getByText('CO-8');
    expect(
      overdue.compareDocumentPosition(upcoming) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('flags entitlement at risk in red when a required notice has no proof on file', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: /Time bar/i }));

    const flag = await screen.findByText('Entitlement at risk');
    expect(flag).toHaveClass('text-semantic-error');
    // The required notice with nothing served is called out on the row.
    expect(screen.getByText('No notice on file')).toBeInTheDocument();
  });

  it('passes the selected contract standard through to the endpoint', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: /Time bar/i }));
    await screen.findByText('VR-7');

    fireEvent.change(screen.getByLabelText('Contract standard'), { target: { value: 'NEC' } });
    await waitFor(() => {
      expect(getNoticeRegister).toHaveBeenCalledWith('p-1', { standard: 'NEC' });
    });
  });
});
