// @ts-nocheck
/**
 * CashFlowWaterfall (task #140) — renders monthly buckets with
 * scheduled / collected / disbursed series.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api')>();
  return {
    ...actual,
    getCashflowWaterfall: vi.fn(),
  };
});

import { getCashflowWaterfall } from '../../api';
import { CashFlowWaterfall } from '../CashFlowWaterfall';

const sample = {
  development_id: 'dev-1',
  start_month: '2026-05',
  months: 3,
  currencies: ['EUR'],
  series: [
    {
      month: '2026-05',
      scheduled: [{ currency: 'EUR', amount: 60000 }],
      actual_collected: [{ currency: 'EUR', amount: 60000 }],
      actual_disbursed: [{ currency: 'EUR', amount: 15000 }],
    },
    {
      month: '2026-06',
      scheduled: [],
      actual_collected: [],
      actual_disbursed: [],
    },
  ],
  totals: {
    scheduled: [{ currency: 'EUR', amount: 60000 }],
    actual_collected: [{ currency: 'EUR', amount: 60000 }],
    actual_disbursed: [{ currency: 'EUR', amount: 15000 }],
  },
};

describe('CashFlowWaterfall', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders monthly buckets with three series labels', async () => {
    (getCashflowWaterfall as ReturnType<typeof vi.fn>).mockResolvedValue(sample);
    render(<CashFlowWaterfall developmentId="dev-1" monthsWindow={3} />);
    await waitFor(() =>
      expect(screen.getByText('2026-05')).toBeInTheDocument(),
    );
    expect(screen.getByText('2026-06')).toBeInTheDocument();
    expect(screen.getAllByText(/Scheduled/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Collected/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Disbursed/).length).toBeGreaterThan(0);
  });
});
