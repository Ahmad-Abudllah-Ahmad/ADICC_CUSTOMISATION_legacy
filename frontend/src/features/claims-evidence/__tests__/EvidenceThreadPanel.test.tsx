// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock the feature api so no network happens. reconstructTypeForKind is kept
// from the real module (it is a pure map) so the mapping test exercises it.
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    reconstructChange: vi.fn(),
    exportReconstructedPack: vi.fn(),
  };
});

// Mock the shared http client so getErrorMessage stays a simple stringifier.
vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  getErrorMessage: (e: unknown) => String(e),
}));

import { exportReconstructedPack, reconstructChange, reconstructTypeForKind } from '../api';
import { EvidenceThreadPanel } from '../EvidenceThreadPanel';
import type { EvidencePack } from '../types';

const PACK: EvidencePack = {
  subject_ref: 'change_order:co-1',
  basis: 'dispute',
  entry_count: 2,
  date_from: '2026-05-30T10:00:00+00:00',
  date_to: '2026-05-31T00:00:00+00:00',
  sections: [
    {
      name: 'variations',
      entries: [
        {
          ref_id: 'co-1',
          source_module: 'changeorders',
          kind: 'change_order',
          title: 'Relocate the site access gate',
          occurred_at: '2026-05-30T10:00:00+00:00',
          actor_id: null,
          summary: '',
        },
      ],
    },
    {
      name: 'correspondence',
      entries: [
        {
          ref_id: 'cor-1',
          source_module: 'correspondence',
          kind: 'correspondence',
          title: 'Re: CO-14 relocate access gate',
          occurred_at: '2026-05-31T00:00:00+00:00',
          actor_id: null,
          summary: '',
        },
      ],
    },
  ],
  content_digest: 'abcdef0123456789',
};

const EMPTY_PACK: EvidencePack = {
  subject_ref: 'change_order:co-9',
  basis: 'dispute',
  entry_count: 0,
  date_from: null,
  date_to: null,
  sections: [],
  content_digest: 'deadbeefcafefeed',
};

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <EvidenceThreadPanel projectId="p-1" subjectType="change_order" subjectId="co-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(reconstructChange).mockResolvedValue(PACK);
  vi.mocked(exportReconstructedPack).mockResolvedValue(PACK);
});

describe('reconstructTypeForKind', () => {
  it('maps the provability kinds onto the reconciliation record types', () => {
    expect(reconstructTypeForKind('change_order')).toBe('change_order');
    expect(reconstructTypeForKind('variation_request')).toBe('variation_request');
    expect(reconstructTypeForKind('variation_order')).toBe('variation_order');
    // The two that differ between the vocabularies.
    expect(reconstructTypeForKind('variation_notice')).toBe('notice');
    expect(reconstructTypeForKind('moc_entry')).toBe('moc');
  });

  it('returns null for a kind with no reconcilable mapping', () => {
    expect(reconstructTypeForKind('something_else')).toBeNull();
  });
});

describe('EvidenceThreadPanel', () => {
  it('defers the fetch until the action is triggered', () => {
    renderPanel();
    // The action is present but nothing has been fetched yet.
    expect(screen.getByText(/Reconstruct evidence thread/i)).toBeInTheDocument();
    expect(reconstructChange).not.toHaveBeenCalled();
  });

  it('renders the reconciled sections and records once reconstructed', async () => {
    renderPanel();
    fireEvent.click(screen.getByText(/Reconstruct evidence thread/i));
    await waitFor(() => {
      expect(screen.getByText('Relocate the site access gate')).toBeInTheDocument();
    });
    expect(reconstructChange).toHaveBeenCalledWith('p-1', 'change_order', 'co-1');
    // Both sections and the linked-record count surface. "Correspondence" shows
    // both as a section header and as the entry's kind badge, so match all.
    expect(screen.getByText(/Variations/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Correspondence/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/2 linked record/i)).toBeInTheDocument();
    // The content digest is shown (truncated), proving the pack is reproducible.
    expect(screen.getByText(/abcdef012345/i)).toBeInTheDocument();
  });

  it('records the assembly when the reconstructed pack is exported', async () => {
    renderPanel();
    fireEvent.click(screen.getByText(/Reconstruct evidence thread/i));
    await waitFor(() => {
      expect(screen.getByText('Relocate the site access gate')).toBeInTheDocument();
    });
    // The Export button appears once a non-empty pack is loaded; clicking it
    // records the deliberate "assemble an evidence pack" action.
    fireEvent.click(screen.getByRole('button', { name: /Export/i }));
    await waitFor(() => {
      expect(exportReconstructedPack).toHaveBeenCalledWith('p-1', 'change_order', 'co-1');
    });
  });

  it('shows an empty state when nothing is linked yet', async () => {
    vi.mocked(reconstructChange).mockResolvedValue(EMPTY_PACK);
    renderPanel();
    fireEvent.click(screen.getByText(/Reconstruct evidence thread/i));
    await waitFor(() => {
      expect(screen.getByText(/Nothing linked yet/i)).toBeInTheDocument();
    });
  });

  it('surfaces an error from the endpoint', async () => {
    vi.mocked(reconstructChange).mockRejectedValue(new Error('boom'));
    renderPanel();
    fireEvent.click(screen.getByText(/Reconstruct evidence thread/i));
    await waitFor(() => {
      expect(screen.getByText(/boom/i)).toBeInTheDocument();
    });
  });
});
