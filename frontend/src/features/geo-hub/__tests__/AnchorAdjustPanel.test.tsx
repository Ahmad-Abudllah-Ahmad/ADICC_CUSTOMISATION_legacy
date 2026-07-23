// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * AnchorAdjustPanel tests - focused on the #284 follow-up "the anchor card
 * masks the map" fix (item 7).
 *
 * The panel must be collapsible to a small pill (so it stops covering the
 * canvas) and remember that choice across mounts via a versioned
 * localStorage key, mirroring OverlayPanel / TilesetSidebar.
 *
 * Coverage:
 *   1. Renders expanded by default with a collapse control.
 *   2. Collapsing swaps the panel for a pill and writes the LS flag.
 *   3. A fresh mount reads the persisted flag and starts collapsed; the
 *      pill expands back to the full panel.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Stub the geo api so nothing hits a real endpoint if a button is pressed.
vi.mock('../api', () => ({
  autoAnchorFromAddress: vi.fn(async () => ({
    anchor: { id: 'a1' },
    precision: 'address',
    source: 'nominatim',
    display_name: 'Somewhere',
  })),
}));

import { AnchorAdjustPanel } from '../AnchorAdjustPanel';
import type { GeoAnchor } from '../types';

const LS_KEY = 'oe.geo_hub.anchor_panel_collapsed.v1';

const ANCHOR: GeoAnchor = {
  id: 'anchor-1',
  project_id: '11111111-2222-3333-4444-555555555555',
  lat: '52.52000',
  lon: '13.40500',
  alt: '0',
  epsg_code: 4326,
  region_code: null,
  address: 'Somewhere, Berlin',
  accuracy_m: null,
  metadata: { geocode_precision: 'address', geocode_source: 'nominatim' },
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

function renderPanel() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <AnchorAdjustPanel
        projectId={ANCHOR.project_id}
        anchor={ANCHOR}
        dragMode={false}
        onToggleDragMode={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('AnchorAdjustPanel - collapse (#284)', () => {
  it('renders expanded with a collapse control by default', () => {
    renderPanel();
    expect(screen.getByTestId('geo-anchor-adjust-panel')).toBeInTheDocument();
    expect(
      screen.getByTestId('geo-anchor-adjust-collapse'),
    ).toBeInTheDocument();
    // No pill while expanded.
    expect(screen.queryByTestId('geo-anchor-adjust-pill')).toBeNull();
  });

  it('collapses to a pill and persists the choice', async () => {
    renderPanel();
    await userEvent.click(screen.getByTestId('geo-anchor-adjust-collapse'));

    // Full panel is gone; pill is shown.
    expect(screen.queryByTestId('geo-anchor-adjust-panel')).toBeNull();
    expect(screen.getByTestId('geo-anchor-adjust-pill')).toBeInTheDocument();
    expect(window.localStorage.getItem(LS_KEY)).toBe('1');
  });

  it('starts collapsed when the persisted flag is set, and expands back', async () => {
    window.localStorage.setItem(LS_KEY, '1');
    renderPanel();

    // Boots as a pill (persisted preference honoured).
    const pill = screen.getByTestId('geo-anchor-adjust-pill');
    expect(pill).toBeInTheDocument();
    expect(screen.queryByTestId('geo-anchor-adjust-panel')).toBeNull();

    await userEvent.click(pill);
    expect(screen.getByTestId('geo-anchor-adjust-panel')).toBeInTheDocument();
    expect(window.localStorage.getItem(LS_KEY)).toBe('0');
  });
});
