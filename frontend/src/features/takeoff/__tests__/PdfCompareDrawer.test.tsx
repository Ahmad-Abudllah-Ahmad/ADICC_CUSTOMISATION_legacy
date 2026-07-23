// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Tests for the PDF revision-compare -> variation handoff (Item 17).
 *
 * Mirrors DwgDrawingCompareDrawer.test.tsx for the PDF path:
 *   1. The "Create variation from delta" button is DISABLED when the diff
 *      reports no measurement changes.
 *   2. It is ENABLED with at least one change, and clicking it calls
 *      takeoffApi.createVariation with the project + document ids.
 *   3. On success a toast names the created draft code and offers a
 *      "View variation" action.
 */

// @ts-nocheck
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { PdfCompareDrawer } from '../PdfCompareDrawer';
import { takeoffApi } from '../api';
import { useToastStore } from '@/stores/useToastStore';

vi.mock('../api', () => ({
  takeoffApi: {
    compare: vi.fn(),
    createVariation: vi.fn(),
  },
}));

const DOCS = [
  { id: 'doc-b', filename: 'rev-b.pdf', pages: 3 },
  { id: 'doc-a', filename: 'rev-a.pdf', pages: 3 },
];

function diff(net: string | null, modified: number) {
  return {
    project_id: 'p1',
    from_document_id: 'doc-a',
    to_document_id: 'doc-b',
    measurement_rows: [],
    summary: {
      measurements: { added: 0, removed: 0, modified, unchanged: 4 },
      net_cost_impact: net,
      cost_currency: net ? 'EUR' : null,
      from_measurement_count: 4,
      to_measurement_count: 4 + modified,
    },
  };
}

function renderDrawer() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PdfCompareDrawer open onClose={vi.fn()} projectId="p1" documents={DOCS} />
    </QueryClientProvider>,
  );
}

describe('PdfCompareDrawer - create variation handoff', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useToastStore.setState({ toasts: [], history: [] });
  });

  it('disables the button when there are no changes', async () => {
    (takeoffApi.compare as unknown as vi.Mock).mockResolvedValue(diff(null, 0));
    renderDrawer();
    const btn = await screen.findByTestId('takeoff-compare-create-variation');
    await waitFor(() => expect((btn as HTMLButtonElement).disabled).toBe(true));
    expect(takeoffApi.createVariation).not.toHaveBeenCalled();
  });

  it('calls createVariation with the project + document ids on click', async () => {
    (takeoffApi.compare as unknown as vi.Mock).mockResolvedValue(diff('500.00', 1));
    (takeoffApi.createVariation as unknown as vi.Mock).mockResolvedValue({
      variation_request_id: 'vr-1',
      code: 'VR-007',
      estimated_cost_impact: '500.00',
      currency: 'EUR',
    });
    renderDrawer();

    const btn = await screen.findByTestId('takeoff-compare-create-variation');
    await waitFor(() => expect((btn as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(btn);

    await waitFor(() =>
      expect(takeoffApi.createVariation).toHaveBeenCalledWith('p1', 'doc-a', 'doc-b'),
    );
  });

  it('shows a success toast with a View variation action', async () => {
    (takeoffApi.compare as unknown as vi.Mock).mockResolvedValue(diff('500.00', 1));
    (takeoffApi.createVariation as unknown as vi.Mock).mockResolvedValue({
      variation_request_id: 'vr-1',
      code: 'VR-007',
      estimated_cost_impact: '500.00',
      currency: 'EUR',
    });
    renderDrawer();

    const btn = await screen.findByTestId('takeoff-compare-create-variation');
    await waitFor(() => expect((btn as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(btn);

    await waitFor(() => {
      const { toasts } = useToastStore.getState();
      expect(toasts.length).toBe(1);
      expect(toasts[0].type).toBe('success');
      expect(typeof toasts[0].action?.onClick).toBe('function');
    });
  });
});
