// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <EscalationNotice /> — the live SLA-escalation banner (#17).
//
// The component reads GET /approval-routes/instances/{id}/escalation and
// mirrors the backend EscalationOut. Coverage:
//   1. No SLA clock on the current step -> renders nothing.
//   2. On time -> renders nothing.
//   3. Overdue inside the grace window -> warning chip + "still inside the
//      grace window" + "{{h}}h overdue", no escalation line.
//   4. Past grace with a next target -> critical chip + "escalating to the
//      next approver (level N)".
//   5. Chain exhausted -> "no further approver to escalate to".
//   6. The fetcher hits the exact instance-scoped escalation URL.

import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { Escalation } from '../types';

/* ── i18n shim — return defaultValue with interpolation. ────────────── */

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (
      _key: string,
      opts?: { defaultValue?: string } & Record<string, unknown>,
    ) => {
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

/* ── API mock ─────────────────────────────────────────────────────── */

const apiMocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
  getErrorMessage: (e: unknown) => String(e),
}));
vi.mock('@/shared/lib/api', () => apiMocks);

import { EscalationNotice } from '../EscalationNotice';

/* ── Fixtures + helpers ────────────────────────────────────────────── */

function esc(overrides: Partial<Escalation> = {}): Escalation {
  return {
    instance_id: 'inst-1',
    target_kind: 'variation',
    current_step_ordinal: 1,
    has_sla: true,
    severity: 'critical',
    hours_overdue: 50,
    should_escalate: true,
    next_target: 'user-2',
    level: 1,
    reason: 'escalate',
    chain_length: 2,
    current_holder: 'user-1',
    ...overrides,
  };
}

function renderNotice(instanceId = 'inst-1') {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <EscalationNotice instanceId={instanceId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => {
  cleanup();
});

/* ── Tests ─────────────────────────────────────────────────────────── */

describe('EscalationNotice', () => {
  it('renders nothing when the current step has no SLA clock', async () => {
    apiMocks.apiGet.mockResolvedValue(
      esc({ has_sla: false, severity: 'on_time', should_escalate: false }),
    );
    renderNotice();
    await waitFor(() => expect(apiMocks.apiGet).toHaveBeenCalled());
    expect(screen.queryByTestId('escalation-notice')).toBeNull();
  });

  it('renders nothing while the step is on time', async () => {
    apiMocks.apiGet.mockResolvedValue(
      esc({ severity: 'on_time', hours_overdue: 0, should_escalate: false }),
    );
    renderNotice();
    await waitFor(() => expect(apiMocks.apiGet).toHaveBeenCalled());
    expect(screen.queryByTestId('escalation-notice')).toBeNull();
  });

  it('shows a warning chip and overdue hours inside the grace window', async () => {
    apiMocks.apiGet.mockResolvedValue(
      esc({
        severity: 'late',
        hours_overdue: 6,
        should_escalate: false,
        next_target: null,
        reason: 'within_window',
        level: 0,
      }),
    );
    renderNotice();

    const banner = await screen.findByTestId('escalation-notice');
    expect(banner).toBeInTheDocument();
    expect(screen.getByText(/Running late/i)).toBeInTheDocument();
    expect(
      screen.getByText(/inside the escalation grace window/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/6h overdue/i)).toBeInTheDocument();
    // Within the window it must NOT claim an escalation is happening.
    expect(
      screen.queryByText(/escalating to the next approver/i),
    ).toBeNull();
  });

  it('announces escalation to the next approver past the grace window', async () => {
    apiMocks.apiGet.mockResolvedValue(
      esc({ severity: 'critical', level: 2, should_escalate: true, next_target: 'user-3' }),
    );
    renderNotice();

    await screen.findByTestId('escalation-notice');
    expect(screen.getByText(/Critically overdue/i)).toBeInTheDocument();
    expect(
      screen.getByText(/escalating to the next approver \(level 2\)/i),
    ).toBeInTheDocument();
  });

  it('reports when the escalation chain is exhausted', async () => {
    apiMocks.apiGet.mockResolvedValue(
      esc({
        severity: 'critical',
        should_escalate: false,
        next_target: null,
        reason: 'chain_exhausted',
      }),
    );
    renderNotice();

    await screen.findByTestId('escalation-notice');
    expect(
      screen.getByText(/no further approver to escalate to/i),
    ).toBeInTheDocument();
  });

  it('fetches from the instance-scoped escalation endpoint', async () => {
    apiMocks.apiGet.mockResolvedValue(esc());
    renderNotice('inst-9');
    await waitFor(() =>
      expect(apiMocks.apiGet).toHaveBeenCalledWith(
        '/v1/approval-routes/instances/inst-9/escalation',
      ),
    );
  });
});
