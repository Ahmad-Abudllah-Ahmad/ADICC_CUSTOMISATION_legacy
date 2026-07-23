// @ts-nocheck
/**
 * BuyerJourneyTimeline (task #140) — renders an ordered timeline with
 * lead/reservation/spa/payment_schedule/handover events.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api')>();
  return {
    ...actual,
    getBuyerJourney: vi.fn(),
  };
});

import { getBuyerJourney } from '../../api';
import { BuyerJourneyTimeline } from '../BuyerJourneyTimeline';

const sample = {
  buyer_id: 'buyer-1',
  development_id: 'dev-1',
  full_name: 'Jane Buyer',
  status: 'contracted',
  event_count: 4,
  events: [
    {
      code: 'lead_created',
      label: 'Lead created',
      timestamp: '2026-01-10T00:00:00Z',
      state: 'completed',
      entity: 'lead',
      entity_id: 'lead-1',
      detail: {},
    },
    {
      code: 'reservation',
      label: 'Reservation RES-1',
      timestamp: '2026-02-01T00:00:00Z',
      state: 'completed',
      entity: 'reservation',
      entity_id: 'res-1',
      detail: {},
    },
    {
      code: 'spa_signed',
      label: 'SPA SPA-1',
      timestamp: '2026-03-15',
      state: 'completed',
      entity: 'sales_contract',
      entity_id: 'spa-1',
      detail: {},
    },
    {
      code: 'payment_schedule',
      label: 'Payment schedule (1/4 paid)',
      timestamp: '2026-04-01',
      state: 'in_progress',
      entity: 'payment_schedule',
      entity_id: 'sched-1',
      detail: {},
    },
  ],
};

describe('BuyerJourneyTimeline', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders cross-entity events in order', async () => {
    (getBuyerJourney as ReturnType<typeof vi.fn>).mockResolvedValue(sample);
    render(<BuyerJourneyTimeline buyerId="buyer-1" />);
    await waitFor(() =>
      expect(screen.getByText('Jane Buyer')).toBeInTheDocument(),
    );
    expect(screen.getByText(/Lead created/)).toBeInTheDocument();
    expect(screen.getByText(/Reservation RES-1/)).toBeInTheDocument();
    expect(screen.getByText(/SPA SPA-1/)).toBeInTheDocument();
    expect(screen.getByText(/Payment schedule/)).toBeInTheDocument();
  });
});
