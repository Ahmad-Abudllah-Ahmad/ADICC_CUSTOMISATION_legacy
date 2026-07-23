// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Pure effective-quantity math tests (issue #332 wave).
 *
 * Pins the single helper the ledger, legend, exports and linked-BOQ push all
 * route through, so slope / wastage / typical-multiplier and the opening-
 * deduction sign fold into one consistent reported number everywhere.
 */
import { describe, it, expect } from 'vitest';
import {
  normalizeSlopeFactor,
  slopeFactorFromDegrees,
  degreesFromSlopeFactor,
  normalizeMultiplier,
  normalizeWastagePct,
  quantityFactor,
  hasQuantityFactor,
  effectiveQuantity,
  reportedMagnitude,
  quantityAdjustmentLabel,
} from '@/features/takeoff/lib/takeoff-quantity';
import type { Measurement } from '@/features/takeoff/lib/takeoff-types';

/** Minimal measurement factory; override just the fields a test cares about. */
function mk(partial: Partial<Measurement>): Measurement {
  return {
    id: 'm1',
    type: 'area',
    points: [],
    value: 10,
    unit: 'm²',
    label: '',
    annotation: '',
    page: 1,
    group: 'General',
    ...partial,
  };
}

describe('normalizeSlopeFactor', () => {
  it('defaults to 1 for unset / sub-1 / non-finite input', () => {
    expect(normalizeSlopeFactor(undefined)).toBe(1);
    expect(normalizeSlopeFactor(null)).toBe(1);
    expect(normalizeSlopeFactor(0.5)).toBe(1); // a slope never shrinks area
    expect(normalizeSlopeFactor(0)).toBe(1);
    expect(normalizeSlopeFactor(-2)).toBe(1);
    expect(normalizeSlopeFactor(NaN)).toBe(1);
  });

  it('keeps a valid factor >= 1', () => {
    expect(normalizeSlopeFactor(1)).toBe(1);
    expect(normalizeSlopeFactor(1.4142)).toBeCloseTo(1.4142, 4);
  });
});

describe('slopeFactorFromDegrees', () => {
  it('flat 0 degrees is 1', () => {
    expect(slopeFactorFromDegrees(0)).toBeCloseTo(1, 6);
  });

  it('45 degrees is sqrt(2)', () => {
    expect(slopeFactorFromDegrees(45)).toBeCloseTo(Math.SQRT2, 6);
  });

  it('60 degrees is 2 (1 / cos 60)', () => {
    expect(slopeFactorFromDegrees(60)).toBeCloseTo(2, 6);
  });

  it('clamps away from 90 so the factor never blows up to Infinity', () => {
    const f = slopeFactorFromDegrees(90);
    expect(Number.isFinite(f)).toBe(true);
    expect(f).toBeGreaterThan(1);
  });

  it('falls back to 1 for non-finite input', () => {
    expect(slopeFactorFromDegrees(NaN)).toBe(1);
    expect(slopeFactorFromDegrees(Infinity)).toBe(1);
  });
});

describe('degreesFromSlopeFactor', () => {
  it('is the inverse of slopeFactorFromDegrees', () => {
    for (const deg of [0, 10, 30, 45, 60]) {
      const back = degreesFromSlopeFactor(slopeFactorFromDegrees(deg));
      expect(back).toBeCloseTo(deg, 4);
    }
  });

  it('a flat factor <= 1 maps to 0 degrees', () => {
    expect(degreesFromSlopeFactor(1)).toBe(0);
    expect(degreesFromSlopeFactor(0.5)).toBe(0);
    expect(degreesFromSlopeFactor(NaN)).toBe(0);
  });
});

describe('normalizeMultiplier', () => {
  it('defaults to 1 and floors to a positive integer', () => {
    expect(normalizeMultiplier(undefined)).toBe(1);
    expect(normalizeMultiplier(3)).toBe(3);
    expect(normalizeMultiplier(2.9)).toBe(2); // cannot have 2.9 typical floors
    expect(normalizeMultiplier(0)).toBe(1);
    expect(normalizeMultiplier(-5)).toBe(1);
    expect(normalizeMultiplier(NaN)).toBe(1);
  });
});

describe('normalizeWastagePct', () => {
  it('defaults to 0 and rejects negatives / non-finite', () => {
    expect(normalizeWastagePct(undefined)).toBe(0);
    expect(normalizeWastagePct(10)).toBe(10);
    expect(normalizeWastagePct(0)).toBe(0);
    expect(normalizeWastagePct(-3)).toBe(0);
    expect(normalizeWastagePct(NaN)).toBe(0);
  });
});

describe('quantityFactor', () => {
  it('is exactly 1 when nothing is set (zero behaviour change)', () => {
    expect(quantityFactor(mk({}))).toBe(1);
  });

  it('applies slope only to area measurements', () => {
    expect(quantityFactor(mk({ type: 'area', slopeFactor: 1.5 }))).toBeCloseTo(1.5, 6);
    // A non-area measurement ignores slopeFactor entirely.
    expect(quantityFactor(mk({ type: 'distance', slopeFactor: 2, unit: 'm' }))).toBe(1);
  });

  it('applies wastage and multiplier to any measurable type', () => {
    expect(quantityFactor(mk({ type: 'distance', unit: 'm', wastagePct: 10 }))).toBeCloseTo(1.1, 6);
    expect(quantityFactor(mk({ type: 'count', unit: 'pcs', multiplier: 3 }))).toBe(3);
  });

  it('composes slope x wastage x multiplier multiplicatively', () => {
    const f = quantityFactor(mk({ type: 'area', slopeFactor: 1.5, wastagePct: 10, multiplier: 2 }));
    expect(f).toBeCloseTo(1.5 * 1.1 * 2, 6); // 3.3
  });
});

describe('hasQuantityFactor', () => {
  it('is false at the identity and true once a factor is applied', () => {
    expect(hasQuantityFactor(mk({}))).toBe(false);
    expect(hasQuantityFactor(mk({ multiplier: 2 }))).toBe(true);
    expect(hasQuantityFactor(mk({ wastagePct: 5 }))).toBe(true);
    expect(hasQuantityFactor(mk({ type: 'area', slopeFactor: 1.2 }))).toBe(true);
    // isDeduction alone is not a quantity FACTOR (it only flips the sign).
    expect(hasQuantityFactor(mk({ isDeduction: true }))).toBe(false);
  });
});

describe('effectiveQuantity', () => {
  it('equals the raw value when no factor is set', () => {
    expect(effectiveQuantity(mk({ value: 12.5 }))).toBe(12.5);
  });

  it('scales an area by its slope factor (true surface)', () => {
    expect(effectiveQuantity(mk({ type: 'area', value: 10, slopeFactor: 1.5 }))).toBeCloseTo(15, 6);
  });

  it('uplifts by wastage percent', () => {
    expect(effectiveQuantity(mk({ type: 'distance', unit: 'm', value: 100, wastagePct: 10 }))).toBeCloseTo(110, 6);
  });

  it('multiplies by the typical multiplier', () => {
    expect(effectiveQuantity(mk({ type: 'count', unit: 'pcs', value: 5, multiplier: 3 }))).toBe(15);
  });

  it('negates an opening deduction (net = gross - openings)', () => {
    expect(effectiveQuantity(mk({ type: 'area', value: 4, isDeduction: true }))).toBe(-4);
    // Factors apply to the magnitude before the sign flip.
    expect(effectiveQuantity(mk({ type: 'area', value: 4, isDeduction: true, multiplier: 2 }))).toBe(-8);
  });

  it('treats a non-finite stored value as 0', () => {
    expect(effectiveQuantity(mk({ value: Number.NaN, multiplier: 3 }))).toBe(0);
  });
});

describe('reportedMagnitude', () => {
  it('is the positive effective quantity (for the BOQ push)', () => {
    expect(reportedMagnitude(mk({ type: 'area', value: 4, isDeduction: true, multiplier: 2 }))).toBe(8);
    expect(reportedMagnitude(mk({ value: 10 }))).toBe(10);
  });
});

describe('quantityAdjustmentLabel', () => {
  it('is empty when nothing is set', () => {
    expect(quantityAdjustmentLabel(mk({}))).toBe('');
  });

  it('summarises each active adjustment', () => {
    expect(quantityAdjustmentLabel(mk({ multiplier: 3 }))).toBe('x3');
    expect(quantityAdjustmentLabel(mk({ wastagePct: 10 }))).toBe('+10%');
    expect(quantityAdjustmentLabel(mk({ type: 'area', slopeFactor: 1.05 }))).toContain('pitch');
  });

  it('combines several adjustments in a stable order', () => {
    expect(quantityAdjustmentLabel(mk({ type: 'area', multiplier: 2, wastagePct: 5 }))).toBe('x2 +5%');
  });

  it('ignores slope on a non-area type', () => {
    expect(quantityAdjustmentLabel(mk({ type: 'distance', unit: 'm', slopeFactor: 2 }))).toBe('');
  });
});
