// @ts-nocheck
/**
 * InventoryHeatmap (task #140) — renders Phase -> Block -> Plot grouping
 * when the API returns the new heatmap shape with phases[] / blocks[].
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api')>();
  return {
    ...actual,
    getInventoryHeatmap: vi.fn(),
  };
});

import { getInventoryHeatmap } from '../../api';
import { InventoryHeatmap } from '../InventoryHeatmap';

const sampleResponse = {
  development_id: 'dev-1',
  currency: 'EUR',
  total_units: 3,
  status_counts: { planned: 2, reserved: 1 },
  phases: [
    {
      phase_id: 'phase-1',
      code: 'P1',
      name: 'Phase Alpha',
      sequence: 1,
      status: 'planned',
      blocks: [
        {
          block_id: 'block-1',
          code: 'A',
          name: 'Tower A',
          levels_count: 2,
          units_per_level: 2,
          orientation: null,
          units: [
            {
              plot_id: 'plot-1',
              plot_number: 'A-101',
              status: 'planned',
              area_m2: 100,
              price_base: 400000,
              currency: 'EUR',
              level_in_block: 1,
              position_on_floor: null,
              house_type_id: null,
            },
            {
              plot_id: 'plot-2',
              plot_number: 'A-102',
              status: 'reserved',
              area_m2: 110,
              price_base: 420000,
              currency: 'EUR',
              level_in_block: 1,
              position_on_floor: null,
              house_type_id: null,
            },
          ],
        },
      ],
    },
    {
      phase_id: null,
      code: '—',
      name: 'Legacy (no phase)',
      sequence: 9999,
      status: 'planned',
      blocks: [
        {
          block_id: null,
          code: '—',
          name: 'Unassigned',
          levels_count: 1,
          units_per_level: 1,
          orientation: null,
          units: [
            {
              plot_id: 'plot-3',
              plot_number: 'LEG-01',
              status: 'planned',
              area_m2: 130,
              price_base: 500000,
              currency: 'EUR',
              level_in_block: null,
              position_on_floor: null,
              house_type_id: null,
            },
          ],
        },
      ],
    },
  ],
};

describe('InventoryHeatmap', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Phase + Block + Plot hierarchy', async () => {
    (getInventoryHeatmap as ReturnType<typeof vi.fn>).mockResolvedValue(
      sampleResponse,
    );
    render(
      <MemoryRouter>
        <InventoryHeatmap developmentId="dev-1" />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText(/Phase Alpha/)).toBeInTheDocument(),
    );
    expect(screen.getByText('Tower A')).toBeInTheDocument();
    expect(screen.getByText('Legacy (no phase)')).toBeInTheDocument();
    expect(screen.getByText('Unassigned')).toBeInTheDocument();
    // Status chips for both statuses present.
    expect(screen.getAllByText(/planned/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/reserved/i).length).toBeGreaterThan(0);
  });

  it('shows empty state when total_units = 0', async () => {
    (getInventoryHeatmap as ReturnType<typeof vi.fn>).mockResolvedValue({
      development_id: 'dev-1',
      currency: 'EUR',
      total_units: 0,
      status_counts: {},
      phases: [],
    });
    render(
      <MemoryRouter>
        <InventoryHeatmap developmentId="dev-1" />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText(/no plots yet/i)).toBeInTheDocument(),
    );
  });
});
