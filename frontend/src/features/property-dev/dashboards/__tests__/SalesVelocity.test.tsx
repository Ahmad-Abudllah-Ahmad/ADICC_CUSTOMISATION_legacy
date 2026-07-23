// @ts-nocheck
/**
 * SalesVelocity (task #140) — renders per-period bars with multi-currency
 * revenue chips.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api')>();
  return {
    ...actual,
    getSalesVelocity: vi.fn(),
  };
});

import { getSalesVelocity } from '../../api';
import { SalesVelocity } from '../SalesVelocity';

const sample = {
  development_id: 'dev-1',
  granularity: 'month',
  currencies: ['EUR', 'USD'],
  series: [
    {
      period: '2026-04',
      units: 2,
      area_m2: 240,
      revenue: [
        { currency: 'EUR', amount: 500000 },
        { currency: 'USD', amount: 600000 },
      ],
    },
  ],
  totals: {
    units: 2,
    area_m2: 240,
    revenue: [
      { currency: 'EUR', amount: 500000 },
      { currency: 'USD', amount: 600000 },
    ],
  },
};

describe('SalesVelocity', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders per-period bars + currency chips', async () => {
    (getSalesVelocity as ReturnType<typeof vi.fn>).mockResolvedValue(sample);
    render(<SalesVelocity developmentId="dev-1" />);
    await waitFor(() =>
      expect(screen.getByText('2026-04')).toBeInTheDocument(),
    );
    expect(screen.getAllByText('EUR').length).toBeGreaterThan(0);
    expect(screen.getAllByText('USD').length).toBeGreaterThan(0);
  });
});
