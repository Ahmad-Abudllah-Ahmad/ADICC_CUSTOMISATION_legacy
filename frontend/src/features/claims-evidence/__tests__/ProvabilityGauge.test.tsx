// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock the feature api so no network happens.
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    getChangeProvability: vi.fn(),
  };
});

// Mock the shared http client so getErrorMessage stays a simple stringifier.
// (apiPost is included for parity with sibling feature tests: the shared UI
// barrel pulls in components that reference it, so the mock must carry it.)
vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  getErrorMessage: (e: unknown) => String(e),
}));

import { getChangeProvability } from '../api';
import { ProvabilityGauge } from '../ProvabilityGauge';
import type { ProvabilityScore } from '../types';

const STRONG: ProvabilityScore = {
  subject_kind: 'variation_notice',
  subject_id: 'n-1',
  subject_ref: 'NOT-1',
  score: 85,
  band: 'strong',
  sub_scores: [
    { signal: 'notice_timeliness', weight: 30, earned: 30, fraction: 1, present: true },
    { signal: 'acknowledgement', weight: 15, earned: 15, fraction: 1, present: true },
    { signal: 'linked_instruction', weight: 20, earned: 20, fraction: 1, present: true },
    { signal: 'ownership_continuity', weight: 15, earned: 0, fraction: 0, present: false },
    { signal: 'date_completeness', weight: 20, earned: 20, fraction: 1, present: true },
  ],
  weaknesses: [
    {
      token: 'no_ownership_chain',
      message: 'No ownership hand-off record exists for this change.',
      signal: 'ownership_continuity',
      points_lost: 15,
    },
  ],
  entry_count: 4,
  date_from: '2026-01-01T00:00:00+00:00',
  date_to: '2026-02-01T00:00:00+00:00',
};

function renderGauge() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProvabilityGauge projectId="p-1" subjectKind="variation_notice" subjectId="n-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getChangeProvability).mockResolvedValue(STRONG);
});

describe('ProvabilityGauge', () => {
  it('renders the score, band and dated-record span once loaded', async () => {
    renderGauge();
    await waitFor(() => {
      expect(screen.getByText('85')).toBeInTheDocument();
    });
    // Band badge label is humanized from the token.
    expect(screen.getByText(/Strong/i)).toBeInTheDocument();
    expect(screen.getByText(/4 dated record/i)).toBeInTheDocument();
  });

  it('lists each evidence signal with its present / missing state', async () => {
    renderGauge();
    await waitFor(() => {
      expect(screen.getByText(/Notice served on time/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Acknowledged by the other party/i)).toBeInTheDocument();
    expect(screen.getByText(/Clear ownership chain/i)).toBeInTheDocument();
    // The earned/weight figure renders for the missing ownership signal.
    expect(screen.getByText('0/15')).toBeInTheDocument();
  });

  it('shows the cure list for the missing signal', async () => {
    renderGauge();
    await waitFor(() => {
      expect(screen.getByText(/No ownership hand-off record exists/i)).toBeInTheDocument();
    });
  });

  it('surfaces an error from the endpoint', async () => {
    vi.mocked(getChangeProvability).mockRejectedValue(new Error('boom'));
    renderGauge();
    await waitFor(() => {
      expect(screen.getByText(/boom/i)).toBeInTheDocument();
    });
  });
});
