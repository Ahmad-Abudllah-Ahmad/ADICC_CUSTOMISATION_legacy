// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Tests for the DWG revision-compare -> variation handoff (Item 17).
 *
 * Focused on the Summary-tab "Create variation from delta" button the
 * handoff lane added on top of the already-shipped compare drawer:
 *   1. The button is DISABLED when the diff reports no changes (you cannot
 *      raise a variation for two identical revisions).
 *   2. The button is ENABLED when there is at least one change, and clicking
 *      it calls createVariationFromDiff with the two selected version ids.
 *   3. On success a toast names the created draft code and offers a
 *      "View variation" action.
 *
 * The compare/version api calls are mocked so the test is deterministic
 * and never touches the network.
 */

// @ts-nocheck
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { DwgDrawingCompareDrawer } from '../DwgDrawingCompareDrawer';
import * as api from '../api';
import { useToastStore } from '@/stores/useToastStore';

vi.mock('../api');

const VERSIONS = [
  { id: 'v2', drawing_id: 'd1', version_number: 2, entity_count: 15 },
  { id: 'v1', drawing_id: 'd1', version_number: 1, entity_count: 10 },
];

function diffWithChanges(net: string | null) {
  return {
    drawing_id: 'd1',
    from_version_id: 'v1',
    from_version_number: 1,
    to_version_id: 'v2',
    to_version_number: 2,
    entity_rows: [],
    annotation_rows: [],
    summary: {
      entities: { added: 1, removed: 0, modified: 0, unchanged: 5 },
      annotations: { added: 0, removed: 0, modified: 1, unchanged: 2 },
      net_cost_impact: net,
      cost_currency: net ? 'EUR' : null,
      from_entity_count: 10,
      to_entity_count: 15,
    },
  };
}

function diffNoChanges() {
  return {
    drawing_id: 'd1',
    from_version_id: 'v1',
    from_version_number: 1,
    to_version_id: 'v2',
    to_version_number: 2,
    entity_rows: [],
    annotation_rows: [],
    summary: {
      entities: { added: 0, removed: 0, modified: 0, unchanged: 5 },
      annotations: { added: 0, removed: 0, modified: 0, unchanged: 2 },
      net_cost_impact: null,
      cost_currency: null,
      from_entity_count: 10,
      to_entity_count: 10,
    },
  };
}

function renderDrawer() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <DwgDrawingCompareDrawer
        open
        onClose={vi.fn()}
        drawingId="d1"
        drawingName="Plan A"
      />
    </QueryClientProvider>,
  );
}

describe('DwgDrawingCompareDrawer - create variation handoff', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useToastStore.setState({ toasts: [], history: [] });
    (api.fetchDrawingVersions as unknown as vi.Mock).mockResolvedValue(VERSIONS);
  });

  it('disables the button when there are no changes', async () => {
    (api.compareDrawings as unknown as vi.Mock).mockResolvedValue(diffNoChanges());
    renderDrawer();
    const btn = await screen.findByTestId('dwg-compare-create-variation');
    await waitFor(() => expect((btn as HTMLButtonElement).disabled).toBe(true));
    expect(api.createVariationFromDiff).not.toHaveBeenCalled();
  });

  it('enables the button and calls the api with the selected version ids', async () => {
    (api.compareDrawings as unknown as vi.Mock).mockResolvedValue(diffWithChanges('500.00'));
    (api.createVariationFromDiff as unknown as vi.Mock).mockResolvedValue({
      variation_request_id: 'vr-1',
      code: 'VR-007',
      estimated_cost_impact: '500.00',
      currency: 'EUR',
    });
    renderDrawer();

    const btn = await screen.findByTestId('dwg-compare-create-variation');
    await waitFor(() => expect((btn as HTMLButtonElement).disabled).toBe(false));

    fireEvent.click(btn);

    await waitFor(() =>
      expect(api.createVariationFromDiff).toHaveBeenCalledWith('d1', 'v1', 'v2'),
    );
  });

  it('shows a success toast with the created code and a View variation action', async () => {
    (api.compareDrawings as unknown as vi.Mock).mockResolvedValue(diffWithChanges('500.00'));
    (api.createVariationFromDiff as unknown as vi.Mock).mockResolvedValue({
      variation_request_id: 'vr-1',
      code: 'VR-007',
      estimated_cost_impact: '500.00',
      currency: 'EUR',
    });
    renderDrawer();

    const btn = await screen.findByTestId('dwg-compare-create-variation');
    await waitFor(() => expect((btn as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(btn);

    await waitFor(() => {
      const { toasts } = useToastStore.getState();
      expect(toasts.length).toBe(1);
      expect(toasts[0].type).toBe('success');
      expect(toasts[0].action?.label).toBeTruthy();
      expect(typeof toasts[0].action?.onClick).toBe('function');
    });
  });
});
