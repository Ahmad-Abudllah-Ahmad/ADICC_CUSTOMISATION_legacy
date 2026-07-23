// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction

import { describe, expect, it } from 'vitest';
import { componentDisplayNumbers } from './costComponentDisplay';

describe('componentDisplayNumbers', () => {
  it('coerces Decimal-string quantity / unit_rate and derives the missing cost', () => {
    // The exact shape a starter-seed / manual row ships: strings, no `cost`,
    // no `unit`. This is the payload that used to crash the expanded row via
    // `"1.02".toFixed(2)`.
    const out = componentDisplayNumbers({ quantity: '1.02', unit_rate: '3' });
    expect(out.qty).toBeCloseTo(1.02);
    expect(out.unitRate).toBe(3);
    // Derived: 1.02 * 3 = 3.06 (was rendered as '—' before).
    expect(out.lineCost).toBeCloseTo(3.06);
    // Proves the crash is gone: the result is a real number with .toFixed().
    expect(out.qty.toFixed(2)).toBe('1.02');
  });

  it('prefers an explicit positive cost over the derived one', () => {
    const out = componentDisplayNumbers({ quantity: '2', unit_rate: '10', cost: '25' });
    expect(out.lineCost).toBe(25);
  });

  it('accepts native numbers unchanged', () => {
    const out = componentDisplayNumbers({ quantity: 4, unit_rate: 2.5 });
    expect(out.qty).toBe(4);
    expect(out.unitRate).toBe(2.5);
    expect(out.lineCost).toBe(10);
  });

  it('returns zeros (never NaN) for absent / unparseable fields', () => {
    const empty = componentDisplayNumbers({});
    expect(empty).toEqual({ qty: 0, unitRate: 0, lineCost: 0 });

    const junk = componentDisplayNumbers({ quantity: 'n/a', unit_rate: null, cost: undefined });
    expect(junk.qty).toBe(0);
    expect(junk.unitRate).toBe(0);
    expect(junk.lineCost).toBe(0);
    expect(Number.isNaN(junk.lineCost)).toBe(false);
  });

  it('falls back to quantity × unit_rate when cost is zero or negative', () => {
    expect(componentDisplayNumbers({ quantity: '3', unit_rate: '4', cost: '0' }).lineCost).toBe(12);
    expect(componentDisplayNumbers({ quantity: '3', unit_rate: '4', cost: '-5' }).lineCost).toBe(12);
  });
});
