// @ts-nocheck
/**
 * Item #25 — digital handover / closeout package.
 *
 * Verifies the HandoverDocumentsSection:
 *   - lazy-loads the bundle on expand and renders the doc list,
 *   - shows the "Ready" badge when all required docs are delivered,
 *   - shows the "missing" badge with the count when they aren't,
 *   - triggers the ZIP export (authenticated download) on click.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import {
  render,
  screen,
  waitFor,
  fireEvent,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../api', () => ({
  getHandoverBundle: vi.fn(),
  createHandoverDoc: vi.fn(),
  updateHandoverDoc: vi.fn(),
  deleteHandoverDoc: vi.fn(),
  exportHandoverPackage: vi.fn(),
}));

import {
  getHandoverBundle,
  exportHandoverPackage,
} from '../api';
import { HandoverDocumentsSection } from '../HandoverDocumentsSection';

const HANDOVER = {
  id: 'h-1',
  plot_id: 'p-1',
  scheduled_at: '2026-09-15',
  completed_at: null,
  snag_count_at_handover: 0,
  final_check_passed: false,
  keys_handed_over_at: null,
  customer_signature_ref: null,
  notes: null,
  metadata: {},
  created_at: '2026-06-01T00:00:00Z',
  updated_at: '2026-06-01T00:00:00Z',
};

function renderWithProviders(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('HandoverDocumentsSection', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the doc list and a Ready badge when all required docs are delivered', async () => {
    (getHandoverBundle as ReturnType<typeof vi.fn>).mockResolvedValue({
      handover_id: 'h-1',
      docs: [
        {
          id: 'd-1',
          handover_id: 'h-1',
          doc_type: 'warranty',
          title: '10y structural warranty',
          file_url: null,
          is_required: true,
          is_delivered: true,
          delivered_at: '2026-06-02',
          metadata: {},
          created_at: '2026-06-01T00:00:00Z',
          updated_at: '2026-06-02T00:00:00Z',
        },
      ],
      delivered_count: 1,
      required_count: 1,
      missing_required: [],
      ready_for_handover: true,
    });

    renderWithProviders(<HandoverDocumentsSection handover={HANDOVER} />);

    // Expand the section to trigger the lazy bundle fetch.
    fireEvent.click(screen.getByTestId('handover-docs-toggle-h-1'));

    expect(await screen.findByText('10y structural warranty')).toBeInTheDocument();
    expect(screen.getByText(/Ready/i)).toBeInTheDocument();
    expect(getHandoverBundle).toHaveBeenCalledWith('h-1');
  });

  it('warns about missing required documents', async () => {
    (getHandoverBundle as ReturnType<typeof vi.fn>).mockResolvedValue({
      handover_id: 'h-1',
      docs: [
        {
          id: 'd-1',
          handover_id: 'h-1',
          doc_type: 'warranty',
          title: '',
          file_url: null,
          is_required: true,
          is_delivered: false,
          delivered_at: null,
          metadata: {},
          created_at: '2026-06-01T00:00:00Z',
          updated_at: '2026-06-01T00:00:00Z',
        },
      ],
      delivered_count: 0,
      required_count: 1,
      missing_required: ['warranty'],
      ready_for_handover: false,
    });

    renderWithProviders(<HandoverDocumentsSection handover={HANDOVER} />);
    fireEvent.click(screen.getByTestId('handover-docs-toggle-h-1'));

    expect(await screen.findByText(/missing/i)).toBeInTheDocument();
  });

  it('exports the closeout package as a ZIP download', async () => {
    (getHandoverBundle as ReturnType<typeof vi.fn>).mockResolvedValue({
      handover_id: 'h-1',
      docs: [],
      delivered_count: 0,
      required_count: 0,
      missing_required: [],
      ready_for_handover: true,
    });
    (exportHandoverPackage as ReturnType<typeof vi.fn>).mockResolvedValue({
      blob: new Blob(['zip'], { type: 'application/zip' }),
      filename: 'handover_A-12_2026-06-04.zip',
    });

    // jsdom lacks createObjectURL — stub it so the download path runs.
    const origCreate = URL.createObjectURL;
    const origRevoke = URL.revokeObjectURL;
    URL.createObjectURL = vi.fn(() => 'blob:mock');
    URL.revokeObjectURL = vi.fn();

    try {
      renderWithProviders(<HandoverDocumentsSection handover={HANDOVER} />);
      fireEvent.click(screen.getByTestId('handover-docs-toggle-h-1'));

      const exportBtn = await screen.findByTestId('export-handover-h-1');
      fireEvent.click(exportBtn);

      await waitFor(() =>
        expect(exportHandoverPackage).toHaveBeenCalledWith('h-1'),
      );
    } finally {
      URL.createObjectURL = origCreate;
      URL.revokeObjectURL = origRevoke;
    }
  });
});
