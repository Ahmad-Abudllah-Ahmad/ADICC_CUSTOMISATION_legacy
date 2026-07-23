// @ts-nocheck
/**
 * InventoryAgeing (task #140) — renders 4 day-buckets + the new
 * "Reserved, no contract" bucket.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api')>();
  return {
    ...actual,
    getInventoryAgeing: vi.fn(),
  };
});

import { getInventoryAgeing } from '../../api';
import { InventoryAgeing } from '../InventoryAgeing';

const sample = {
  development_id: 'dev-1',
  as_of: '2026-05-22',
  total_unsold: 5,
  buckets: [
    { label: '0–30', count: 2, plots: [] },
    { label: '30–60', count: 1, plots: [] },
    { label: '60–90', count: 0, plots: [] },
    { label: '90+', count: 1, plots: [] },
    {
      label: 'Reserved, no contract',
      count: 1,
      plots: [
        {
          plot_id: 'p1',
          plot_number: 'A-101',
          status: 'planned',
          days_on_market: 14,
          block_id: 'b1',
          house_type_id: null,
          price_base: 400000,
          currency: 'EUR',
        },
      ],
    },
  ],
};

describe('InventoryAgeing', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders 5 buckets including reserved-no-contract', async () => {
    (getInventoryAgeing as ReturnType<typeof vi.fn>).mockResolvedValue(sample);
    render(<InventoryAgeing developmentId="dev-1" />);
    await waitFor(() =>
      expect(screen.getByText('Reserved, no contract')).toBeInTheDocument(),
    );
    expect(screen.getByText('0–30')).toBeInTheDocument();
    expect(screen.getByText('30–60')).toBeInTheDocument();
    expect(screen.getByText('90+')).toBeInTheDocument();
  });
});
