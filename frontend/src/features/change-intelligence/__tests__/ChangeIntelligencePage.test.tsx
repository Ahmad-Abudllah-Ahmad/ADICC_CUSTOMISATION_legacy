// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

// Mock the project-context store so the page resolves a project id without a
// real store. The selector form `useProjectContextStore((s) => s.x)` is honored
// by returning a function that applies the selector to a fixed state.
vi.mock('@/stores/useProjectContextStore', () => ({
  useProjectContextStore: (sel: (s: { activeProjectId: string }) => unknown) =>
    sel({ activeProjectId: 'p-1' }),
}));

// Mock the feature api so no network happens.
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
  };
});

// Mock the shared http client (used for the projects fallback fetch).
vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn().mockResolvedValue([]),
  apiPost: vi.fn(),
  getErrorMessage: (e: unknown) => String(e),
}));

import {
  getCoordinationPlan,
  getCommsDigest,
  getCycleTimeBoard,
  getImpactProjection,
  getRecoveryLedger,
  listBackCharges,
  clarifyChangeNote,
  getDisputeRiskBoard,
  getDecisionImpact,
  getChangeWatch,
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
  vi.mocked(getCoordinationPlan).mockResolvedValue({
    project_id: 'p-1',
    generated_at: '2026-06-24T00:00:00Z',
    total: 2,
    overdue_count: 1,
    due_soon_count: 1,
    steps: [
      {
        ref_id: 'co-1',
        kind: 'change_order',
        title: 'Revised slab detail',
        ball_in_court: 'alice',
        urgency: 'overdue',
        days_to_due: -3,
        recommended_action: 'escalate',
        reason: 'Past the response due date',
        rank_score: 100,
      },
    ],
  });
  vi.mocked(getCycleTimeBoard).mockResolvedValue({
    project_id: 'p-1',
    as_of: '2026-06-24T00:00:00Z',
    total_open: 2,
    total_overdue: 1,
    unassigned_open: 0,
    parties: [
      { party: 'alice', open_count: 2, overdue_count: 1, oldest_age_days: 9, total_age_days: 12, avg_age_days: 6 },
    ],
    items: [],
  });
  vi.mocked(getCommsDigest).mockResolvedValue({
    project_id: 'p-1',
    generated_at: '2026-06-24T00:00:00Z',
    thread_count: 1,
    open_count: 1,
    awaiting_us_count: 1,
    threads: [
      {
        thread_key: 't-1',
        subject: 'Invoice query',
        message_count: 2,
        participants: ['ext', 'us'],
        first_at: '2026-06-20T00:00:00Z',
        last_at: '2026-06-22T00:00:00Z',
        last_direction: 'inbound',
        last_sender: 'ext',
        awaiting: 'us',
        is_open: true,
      },
    ],
  });
  vi.mocked(getImpactProjection).mockResolvedValue({
    project_id: 'p-1',
    approved_count: 1,
    total_schedule_delta_days: 4,
    primary_currency: 'USD',
    primary_currency_cost: '1200.00',
    by_kind: [{ kind: 'change_order', count: 1, total_cost: '1200.00', total_days: 4 }],
    by_currency: [{ currency: 'USD', total_cost: '1200.00', count: 1 }],
  });
  vi.mocked(getRecoveryLedger).mockResolvedValue({
    project_id: 'p-1',
    item_count: 1,
    open_count: 1,
    primary_currency: 'USD',
    primary_outstanding: '500.00',
    by_party: [
      {
        party: 'subcontractor a',
        currency: 'USD',
        item_count: 1,
        open_count: 1,
        gross_total: '700.00',
        chargeable_total: '600.00',
        recovered_total: '100.00',
        outstanding_total: '500.00',
      },
    ],
    by_currency: [{ currency: 'USD', item_count: 1, chargeable_total: '600.00', recovered_total: '100.00', outstanding_total: '500.00' }],
  });
  vi.mocked(listBackCharges).mockResolvedValue([]);
  vi.mocked(clarifyChangeNote).mockResolvedValue({
    title: 'Change request: extra waterproofing',
    normalized_summary: 'Add waterproofing to the basement slab.',
    detected_classification: 'scope_addition',
    // The engine emits 'required' / 'recommended' (not 'high' / 'medium').
    missing: [{ field: 'cost_impact', question: 'What is the cost impact?', severity: 'required' }],
    clause_suggestions: [{ standard: 'FIDIC', clause_ref: '13.1', rationale: 'Variations and adjustments' }],
    suggested_route: 'variation_request',
    completeness: 0.5,
  });
  vi.mocked(getDisputeRiskBoard).mockResolvedValue({
    project_id: 'p-1',
    generated_at: '2026-06-24T00:00:00Z',
    items: [
      {
        change_id: 'co-9',
        change_ref: 'CO-9',
        kind: 'change_order',
        title: 'Contested slab rework',
        exposure_score: 72,
        band: 'high',
        dominant_driver: 'weak_evidence',
        recommended_cure: 'Strengthen the contemporaneous record before this change is contested.',
        intrinsic_exposure: 0.45,
        money_multiplier: 1.6,
        money_basis: '200000.00',
        currency: 'EUR',
        factors: [
          { name: 'evidence', weight: 55, fraction: 0.85, weighted: 46.75, is_driver: true },
          { name: 'overdue_age', weight: 20, fraction: 0.5, weighted: 10, is_driver: false },
          { name: 'sla_breach', weight: 15, fraction: 0, weighted: 0, is_driver: false },
          { name: 'ownership', weight: 10, fraction: 0, weighted: 0, is_driver: false },
        ],
      },
    ],
    summary: {
      item_count: 1,
      band_counts: { high: 1, elevated: 0, low: 0 },
      by_currency: [
        { currency: 'EUR', item_count: 1, money_basis_total: '200000.00', exposure_weighted_amount: '144000.00' },
      ],
      top_driver_counts: { weak_evidence: 1 },
    },
  });
  vi.mocked(getDecisionImpact).mockResolvedValue({
    project_id: 'p-1',
    candidate_change_id: 'co-cand',
    candidate_kind: 'change_order',
    candidate_currency: 'EUR',
    rows: [
      {
        kind: 'change_order',
        currency: 'EUR',
        current_committed_cost: '1500.00',
        candidate_cost_delta: '250.00',
        resulting_cost: '1750.00',
        current_committed_days: '8',
        candidate_days_delta: '2',
        resulting_days: '10',
      },
    ],
    totals_by_currency: [
      {
        currency: 'EUR',
        current_committed_cost: '1500.00',
        candidate_cost_delta: '250.00',
        resulting_cost: '1750.00',
        current_committed_days: '8',
        candidate_days_delta: '2',
        resulting_days: '10',
      },
    ],
  });
  vi.mocked(getChangeWatch).mockResolvedValue({
    project_id: 'p-1',
    generated_at: '2026-06-24T00:00:00Z',
    item_count: 2,
    counts: { lost: 0, stalled: 1, incomplete: 0, ok: 1 },
    items: [
      {
        change_id: 'co-stall',
        kind: 'change_order',
        classification: 'stalled',
        reasons: ['stalled_overdue_and_idle'],
        idle_days: 14,
        overdue_days: 6,
      },
      {
        change_id: 'co-ok',
        kind: 'change_order',
        classification: 'ok',
        reasons: [],
        idle_days: 1,
        overdue_days: 0,
      },
    ],
  });
});

describe('ChangeIntelligencePage', () => {
  it('renders the title and the default coordination tab', async () => {
    renderPage();
    expect(screen.getByRole('heading', { name: /Change Intelligence/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Revised slab detail')).toBeInTheDocument();
    });
    // The overdue step carries an escalate recommendation.
    expect(screen.getByText(/escalate/i)).toBeInTheDocument();
  });

  it('switches to the cost recovery tab and shows the ledger', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: /Cost recovery/i }));
    await waitFor(() => {
      expect(screen.getByText('subcontractor a')).toBeInTheDocument();
    });
  });

  it('runs the clarifier and shows the structured draft', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: /Clarifier/i }));
    const box = await screen.findByPlaceholderText(/Paste a quick description/i);
    fireEvent.change(box, { target: { value: 'need extra waterproofing in basement' } });
    fireEvent.click(screen.getByRole('button', { name: /Analyze/i }));
    await waitFor(() => {
      expect(screen.getByText('Change request: extra waterproofing')).toBeInTheDocument();
    });
    expect(screen.getByText(/50% complete/i)).toBeInTheDocument();
  });

  // #3 fix (v8.10.1): the engine emits 'required' / 'recommended' severities;
  // a 'required' gap must render the error-variant badge, not fall through to
  // neutral as the pre-fix 'high' / 'medium' mapping did.
  it('colors a required clarification gap with the error variant', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: /Clarifier/i }));
    const box = await screen.findByPlaceholderText(/Paste a quick description/i);
    fireEvent.change(box, { target: { value: 'need extra waterproofing in basement' } });
    fireEvent.click(screen.getByRole('button', { name: /Analyze/i }));
    const badge = await screen.findByText('required');
    expect(badge).toHaveClass('text-semantic-error');
  });

  it('switches to the dispute risk tab and ranks open changes', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: /Dispute risk/i }));
    await waitFor(() => {
      expect(screen.getByText(/Contested slab rework/i)).toBeInTheDocument();
    });
    // The high-band exposure score and the dominant driver are surfaced.
    expect(screen.getByText('72')).toBeInTheDocument();
    expect(screen.getByText(/Weak Evidence/i)).toBeInTheDocument();
  });

  it('previews a decision impact for a candidate change', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: /Decision impact/i }));
    const box = await screen.findByPlaceholderText(/Paste the id of the change/i);
    fireEvent.change(box, { target: { value: 'co-cand' } });
    fireEvent.click(screen.getByRole('button', { name: /Preview impact/i }));
    await waitFor(() => {
      expect(getDecisionImpact).toHaveBeenCalledWith('p-1', 'co-cand');
    });
    // The resulting EUR position is rendered. Match either thousands separator
    // so the assertion is locale-independent (the store default is de-DE, which
    // groups as 1.750,00, while en-US groups as 1,750.00).
    expect(await screen.findByText(/1[.,]750/)).toBeInTheDocument();
  });

  it('switches to the watch tab and lists drifting changes', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: /^Watch$/i }));
    // The stalled row's overdue figure proves the flagged list rendered (the
    // "Stalled" stat-tile label renders even before data, so assert on the row).
    expect(await screen.findByText(/6d overdue/i)).toBeInTheDocument();
    // The stalled row's reason token is humanized into the row.
    expect(screen.getByText(/Stalled Overdue And Idle/i)).toBeInTheDocument();
  });
});
