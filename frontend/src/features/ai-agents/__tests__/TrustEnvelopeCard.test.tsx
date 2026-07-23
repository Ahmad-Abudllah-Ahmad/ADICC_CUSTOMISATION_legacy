// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <TrustEnvelopeCard /> - the per-run trust surface that makes the
// AI trust moat visible. It renders the agent's structured trust envelope
// (calibrated confidence, rationale, cited sources, what would increase
// confidence) and closes the loop with a verdict the user records, which feeds
// the accuracy scoreboard.
//
// Coverage:
//   1. Renders confidence %, rationale, a cited source and the "to be more
//      sure" hint from a populated envelope.
//   2. Clicking Correct posts the verdict (correct: true) for the run.
//   3. An already-recorded verdict shows the recorded state + note (no buttons).
//   4. A run with no envelope (or still running) renders nothing.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { AgentRun } from '../api';

/* -- Toast mock ------------------------------------------------------- */

const toastMocks = vi.hoisted(() => ({ addToast: vi.fn() }));
vi.mock('@/stores/useToastStore', () => ({
  useToastStore: Object.assign(
    (selector: (s: { addToast: typeof toastMocks.addToast }) => unknown) =>
      selector({ addToast: toastMocks.addToast }),
    { getState: () => ({ addToast: toastMocks.addToast }) },
  ),
}));

/* -- i18n shim - return defaultValue with interpolation. -------------- */

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string } & Record<string, unknown>) => {
      if (typeof opts === 'object' && opts && 'defaultValue' in opts) {
        let dv = String(opts.defaultValue ?? '');
        for (const [k, v] of Object.entries(opts)) {
          if (k === 'defaultValue') continue;
          dv = dv.replaceAll(`{{${k}}}`, String(v));
        }
        return dv;
      }
      return _key;
    },
    i18n: { language: 'en' },
  }),
  initReactI18next: { type: '3rdParty', init: () => undefined },
  I18nextProvider: ({ children }: { children: unknown }) => children,
  Trans: ({ children }: { children?: unknown }) => children ?? null,
}));

/* -- API mock ------------------------------------------------------- */

const apiMocks = vi.hoisted(() => ({ recordRunOutcome: vi.fn() }));
vi.mock('../api', () => ({
  aiAgentsApi: { recordRunOutcome: apiMocks.recordRunOutcome },
}));

import { TrustEnvelopeCard } from '../components/TrustEnvelopeCard';

function makeRun(overrides?: Partial<AgentRun>): AgentRun {
  return {
    id: 'run-1',
    agent_name: 'estimate_reviewer',
    project_id: null,
    user_id: 'u1',
    status: 'completed',
    trigger_source: 'manual',
    failure_reason: null,
    user_input: 'review the estimate',
    final_output: 'Looks consistent.',
    iterations: 1,
    total_tokens: 100,
    started_at: null,
    finished_at: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    steps: [],
    ...overrides,
  };
}

function renderCard(run: AgentRun) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <TrustEnvelopeCard run={run} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(cleanup);

describe('TrustEnvelopeCard', () => {
  it('renders confidence, rationale, a cited source and the improvement hint', () => {
    renderCard(
      makeRun({
        trust: {
          confidence: 0.8,
          rationale: 'Solid match against the cost book.',
          sources: [{ kind: 'boq', ref: 'BOQ-123', label: 'Concrete works', score: 0.9 }],
          what_would_increase_confidence: 'A site measure of the slab area.',
          model: 'claude-test',
        },
      }),
    );

    expect(screen.getByText('80%')).toBeInTheDocument();
    expect(screen.getByText('Solid match against the cost book.')).toBeInTheDocument();
    expect(screen.getByText('BOQ-123')).toBeInTheDocument();
    expect(screen.getByText(/A site measure of the slab area\./)).toBeInTheDocument();
    // Both verdict buttons are offered when no outcome is recorded yet.
    expect(screen.getByRole('button', { name: 'Correct' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Incorrect' })).toBeInTheDocument();
  });

  it('records a correct verdict for the run', async () => {
    apiMocks.recordRunOutcome.mockResolvedValue({
      run_id: 'run-1',
      agent_name: 'estimate_reviewer',
      actual_outcome: true,
    });
    renderCard(
      makeRun({
        trust: {
          confidence: 0.6,
          rationale: null,
          sources: [],
          what_would_increase_confidence: null,
          model: null,
        },
      }),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Correct' }));

    await waitFor(() =>
      expect(apiMocks.recordRunOutcome).toHaveBeenCalledWith('run-1', {
        correct: true,
        note: undefined,
      }),
    );
  });

  it('shows the recorded verdict and note without offering buttons again', () => {
    renderCard(
      makeRun({
        trust: {
          confidence: 0.7,
          rationale: null,
          sources: [],
          what_would_increase_confidence: null,
          model: null,
          actual_outcome: true,
          outcome_recorded_at: '2026-01-02T00:00:00Z',
          outcome_note: 'Confirmed on site.',
        },
      }),
    );

    expect(screen.getByText(/You marked this correct/)).toBeInTheDocument();
    expect(screen.getByText('Confirmed on site.')).toBeInTheDocument();
    // The verdict buttons are replaced by the recorded state + a Change action.
    expect(screen.queryByRole('button', { name: 'Correct' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Change' })).toBeInTheDocument();
  });

  it('renders nothing for a run with no envelope', () => {
    const { container } = renderCard(makeRun({ trust: null }));
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing while the run is still running', () => {
    const { container } = renderCard(
      makeRun({
        status: 'running',
        trust: {
          confidence: 0.9,
          rationale: 'early',
          sources: [],
          what_would_increase_confidence: null,
          model: null,
        },
      }),
    );
    expect(container).toBeEmptyDOMElement();
  });
});
