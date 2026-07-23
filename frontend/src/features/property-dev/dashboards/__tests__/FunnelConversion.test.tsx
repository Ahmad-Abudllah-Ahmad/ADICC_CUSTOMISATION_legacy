// @ts-nocheck
/**
 * FunnelConversion (task #140) — renders the 5-stage funnel.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api')>();
  return {
    ...actual,
    getFunnelConversion: vi.fn(),
  };
});

import { getFunnelConversion } from '../../api';
import { FunnelConversion } from '../FunnelConversion';

const sample = {
  development_id: 'dev-1',
  period_days: 90,
  stages: [
    { code: 'lead', label: 'Lead', count: 50, drop_pct: 0 },
    { code: 'reservation', label: 'Reservation', count: 20, drop_pct: 60 },
    { code: 'spa_draft', label: 'SPA draft', count: 18, drop_pct: 10 },
    { code: 'spa_signed', label: 'SPA signed', count: 15, drop_pct: 16.7 },
    { code: 'handover', label: 'Handover', count: 10, drop_pct: 33.3 },
  ],
  totals: { leads: 50, conversion_pct: 20.0 },
};

describe('FunnelConversion', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders all 5 stages with counts', async () => {
    (getFunnelConversion as ReturnType<typeof vi.fn>).mockResolvedValue(sample);
    render(<FunnelConversion developmentId="dev-1" />);
    await waitFor(() => expect(screen.getByText('Lead')).toBeInTheDocument());
    expect(screen.getByText('Reservation')).toBeInTheDocument();
    expect(screen.getByText('SPA draft')).toBeInTheDocument();
    expect(screen.getByText('SPA signed')).toBeInTheDocument();
    expect(screen.getByText('Handover')).toBeInTheDocument();
    expect(screen.getByText('50')).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument();
  });
});
