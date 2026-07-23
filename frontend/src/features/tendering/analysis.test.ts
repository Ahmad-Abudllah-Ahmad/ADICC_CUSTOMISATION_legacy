// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, expect, it } from 'vitest';
import { classifyCell, recommend } from './analysis';

describe('classifyCell', () => {
  it('returns null when fewer than 2 priced bids', () => {
    expect(classifyCell(100, [100])).toBeNull();
    expect(classifyCell(100, [100, 0, 0])).toBeNull();
  });

  it('returns null for zero cell', () => {
    expect(classifyCell(0, [100, 110, 105])).toBeNull();
  });

  it('flags high outliers at default 15% threshold', () => {
    expect(classifyCell(150, [100, 105, 95])).toBe('high');
  });

  it('flags low outliers at default 15% threshold', () => {
    expect(classifyCell(70, [100, 105, 95])).toBe('low');
  });

  it('does not flag cells inside the threshold band', () => {
    expect(classifyCell(110, [100, 105, 95])).toBeNull();
    expect(classifyCell(90, [100, 105, 95])).toBeNull();
  });

  it('honours custom threshold', () => {
    expect(classifyCell(110, [100, 105, 95], 0.05)).toBe('high');
  });
});

describe('recommend', () => {
  const base = { currency: 'EUR', deviation_pct: 0, status: 'submitted' };
  it('returns null when no eligible bids', () => {
    expect(recommend([])).toBeNull();
    expect(
      recommend([{ bid_id: '1', company_name: 'X', total: 0, ...base }]),
    ).toBeNull();
  });

  it('single bid → medium confidence, single_bid reason', () => {
    const r = recommend([
      { bid_id: '1', company_name: 'A', total: 100, ...base },
    ]);
    expect(r?.confidence).toBe('medium');
    expect(r?.reasonKey).toBe('single_bid');
    expect(r?.runnerUp).toBeNull();
  });

  it('clear lowest with comfortable gap → high confidence', () => {
    const r = recommend([
      { bid_id: '1', company_name: 'A', total: 100, ...base },
      { bid_id: '2', company_name: 'B', total: 110, ...base },
      { bid_id: '3', company_name: 'C', total: 115, ...base },
    ]);
    expect(r?.confidence).toBe('high');
    expect(r?.reasonKey).toBe('clear_winner');
    expect(r?.winner.company_name).toBe('A');
    expect(r?.runnerUp?.company_name).toBe('B');
    expect(r?.gapAmount).toBe(10);
  });

  it('narrow gap (<2%) → medium confidence', () => {
    const r = recommend([
      { bid_id: '1', company_name: 'A', total: 1000, ...base },
      { bid_id: '2', company_name: 'B', total: 1015, ...base },
      { bid_id: '3', company_name: 'C', total: 1050, ...base },
    ]);
    expect(r?.confidence).toBe('medium');
    expect(r?.reasonKey).toBe('narrow_gap');
  });

  it('lowest >20% under median → low confidence (suspicious)', () => {
    const r = recommend([
      { bid_id: '1', company_name: 'A', total: 50, ...base },
      { bid_id: '2', company_name: 'B', total: 100, ...base },
      { bid_id: '3', company_name: 'C', total: 105, ...base },
    ]);
    expect(r?.confidence).toBe('low');
    expect(r?.reasonKey).toBe('suspicious_low');
    expect(r?.belowMedianPct).toBeGreaterThan(20);
  });

  it('filters rejected bids', () => {
    const r = recommend([
      { bid_id: '1', company_name: 'A', total: 90, ...base, status: 'rejected' },
      { bid_id: '2', company_name: 'B', total: 100, ...base },
    ]);
    expect(r?.winner.company_name).toBe('B');
  });
});
