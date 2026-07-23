// @ts-nocheck
/**
 * InventoryMapPage (task #142) — sales-floor block / floor / unit grid.
 *
 * Coverage:
 *   1. Renders 3 blocks × 4 floors × 12 plots with KPI ribbon counters.
 *   2. Clicking a tile with shift/cmd toggles the selection ring.
 *   3. Shift-clicking a second tile selects the range between them.
 *   4. Keyboard ArrowRight moves focus across tiles.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// ``src/test/setup.ts`` globally mocks ``useParams`` to return ``{}`` — that
// would short-circuit InventoryMapPage into its "No development selected"
// empty state. Override the mock locally so the route param resolves.
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  );
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useParams: () => ({ devId: 'dev-1' }),
    useSearchParams: () => [new URLSearchParams(), vi.fn()],
  };
});

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    getInventoryMap: vi.fn(),
    bulkHoldInventory: vi.fn(),
    bulkReleaseInventory: vi.fn(),
  };
});

import { getInventoryMap } from '../api';
import { InventoryMapPage } from '../InventoryMapPage';

/* ── Fixture: 3 blocks × 4 floors × 1 plot per floor (12 total) ─────── */

function makePlot(
  id: string,
  block: string,
  floor: number,
  status: 'planned' | 'reserved' | 'sold',
) {
  return {
    id,
    unit_code: `${block}-${String(floor).padStart(2, '0')}-A`,
    status,
    plot_type: '2BR',
    block_code: block,
    floor,
    base_price: '350000.00',
    area_m2: '85.00',
    currency: 'EUR',
    bedrooms: 2,
    bathrooms: 1,
  };
}

const SAMPLE = {
  development_id: 'dev-1',
  currency: 'EUR',
  blocks: ['B1', 'B2', 'B3'].map((bc, bIdx) => ({
    block_code: bc,
    block_id: `block-${bIdx}`,
    name: `Tower ${bc}`,
    floors: [4, 3, 2, 1].map((floor) => ({
      floor,
      plots: [
        makePlot(
          `plot-${bc}-${floor}`,
          bc,
          floor,
          floor === 1 ? 'reserved' : floor === 2 ? 'sold' : 'planned',
        ),
      ],
    })),
  })),
  summary: {
    total: 12,
    available: 6,
    reserved: 3,
    sold: 3,
    handed_over: 0,
    held: 0,
    blocked: 0,
    under_construction: 0,
    ready: 0,
  },
};

/* ── Test harness ─────────────────────────────────────────────────── */

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/property-dev/developments/dev-1/inventory-map']}>
        <Routes>
          <Route
            path="/property-dev/developments/:devId/inventory-map"
            element={<InventoryMapPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('InventoryMapPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (getInventoryMap as ReturnType<typeof vi.fn>).mockResolvedValue(SAMPLE);
  });

  it('renders the 3 blocks, 4 floors and 12 plot tiles plus KPI ribbon', async () => {
    renderPage();

    await waitFor(() =>
      expect(screen.getByText('Tower B1')).toBeInTheDocument(),
    );
    expect(screen.getByText('Tower B2')).toBeInTheDocument();
    expect(screen.getByText('Tower B3')).toBeInTheDocument();

    const tiles = screen.getAllByRole('gridcell');
    expect(tiles).toHaveLength(12);

    // KPI ribbon counts present.
    const kpi = screen.getByTestId('inventory-map-kpi');
    expect(within(kpi).getByTestId('kpi-all')).toHaveTextContent('12');
    expect(within(kpi).getByTestId('kpi-available')).toHaveTextContent('6');
    expect(within(kpi).getByTestId('kpi-reserved')).toHaveTextContent('3');
    expect(within(kpi).getByTestId('kpi-sold')).toHaveTextContent('3');
  });

  it('cmd-click toggles a tile into the selection ring', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(screen.getByText('Tower B1')).toBeInTheDocument(),
    );

    const tile = screen.getByTestId('plot-tile-plot-B1-4');
    expect(tile).toHaveAttribute('aria-selected', 'false');

    await user.keyboard('{Meta>}');
    await user.click(tile);
    await user.keyboard('{/Meta}');

    expect(tile).toHaveAttribute('aria-selected', 'true');
    // Floating action bar appears.
    expect(screen.getByTestId('inventory-map-action-bar')).toBeInTheDocument();
  });

  it('shift-clicking a second tile selects the range across visible plots', async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByText('Tower B1')).toBeInTheDocument(),
    );

    const first = screen.getByTestId('plot-tile-plot-B1-4');
    const second = screen.getByTestId('plot-tile-plot-B1-2');

    // First click: anchor (use meta so we don't open the drawer).
    fireEvent.click(first, { metaKey: true });
    expect(first).toHaveAttribute('aria-selected', 'true');

    // Shift-click: extends range. The 3 plots from B1-04 .. B1-02
    // (inclusive on the flat visible list) should now all be selected.
    fireEvent.click(second, { shiftKey: true });
    expect(second).toHaveAttribute('aria-selected', 'true');
    // The intermediate plot is also selected.
    expect(screen.getByTestId('plot-tile-plot-B1-3')).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('keyboard ArrowRight moves focus to the next tile', async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByText('Tower B1')).toBeInTheDocument(),
    );

    const first = screen.getByTestId('plot-tile-plot-B1-4');
    first.focus();
    expect(first).toHaveFocus();

    fireEvent.keyDown(first, { key: 'ArrowRight' });
    // The next plot in the flat visible list is B1-03 (since floors are
    // sorted descending: 4, 3, 2, 1).
    await waitFor(() =>
      expect(screen.getByTestId('plot-tile-plot-B1-3')).toHaveFocus(),
    );
  });
});
