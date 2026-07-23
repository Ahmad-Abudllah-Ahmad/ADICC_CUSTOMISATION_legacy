// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';
import {
  EVM_WARNING_DEFAULTS,
  PERCENT_TYPES,
  pvPercentOfBac,
  rollupSteps,
  totalWeight,
  type StepLike,
} from './progressRigor';
import type { EvmWarningKey } from './api';

describe('rollupSteps', () => {
  it('returns 0 for no steps', () => {
    expect(rollupSteps([])).toBe(0);
  });

  it('weighted-averages step percents (mirrors the backend engine)', () => {
    const steps: StepLike[] = [
      { weight: 3, percent_complete: 100 },
      { weight: 1, percent_complete: 0 },
    ];
    expect(rollupSteps(steps)).toBeCloseTo(75, 5);
  });

  it('falls back to a plain mean when total weight is 0', () => {
    const steps: StepLike[] = [
      { weight: 0, percent_complete: 80 },
      { weight: 0, percent_complete: 40 },
    ];
    expect(rollupSteps(steps)).toBeCloseTo(60, 5);
  });

  it('caps the roll-up below 100 when a milestone step is below 100', () => {
    const steps: StepLike[] = [
      { weight: 1, percent_complete: 100 },
      { weight: 0, percent_complete: 50, is_milestone: true },
    ];
    // Weighted mean from the non-zero weight is 100, but the open milestone caps it.
    expect(rollupSteps(steps)).toBeCloseTo(99.999, 5);
    expect(rollupSteps(steps)).toBeLessThan(100);
  });

  it('does not cap when the milestone is itself complete', () => {
    const steps: StepLike[] = [
      { weight: 1, percent_complete: 100 },
      { weight: 1, percent_complete: 100, is_milestone: true },
    ];
    expect(rollupSteps(steps)).toBeCloseTo(100, 5);
  });

  it('accepts decimal-string weights and percents', () => {
    const steps: StepLike[] = [
      { weight: '2', percent_complete: '50' },
      { weight: '2', percent_complete: '100' },
    ];
    expect(rollupSteps(steps)).toBeCloseTo(75, 5);
  });

  it('clamps the result into 0..100', () => {
    const steps: StepLike[] = [{ weight: 1, percent_complete: 150 }];
    expect(rollupSteps(steps)).toBe(100);
  });
});

describe('totalWeight', () => {
  it('sums step weights as numbers', () => {
    expect(totalWeight([{ weight: '3', percent_complete: 0 }, { weight: 1.5, percent_complete: 0 }])).toBeCloseTo(4.5, 5);
  });
});

describe('pvPercentOfBac', () => {
  it('formats PV as a percent of BAC', () => {
    expect(pvPercentOfBac('500', '1000')).toBe('50.0%');
    expect(pvPercentOfBac(250, 1000)).toBe('25.0%');
  });
  it('returns a dash when BAC is zero or missing', () => {
    expect(pvPercentOfBac('500', '0')).toBe('-');
    expect(pvPercentOfBac('500', null)).toBe('-');
    expect(pvPercentOfBac(null, null)).toBe('-');
  });
});

describe('EVM warning catalogue', () => {
  it('has default text for every warning key', () => {
    const keys: EvmWarningKey[] = [
      'units_type_without_budgeted_units',
      'duration_type_on_nonlinear_cost',
      'physical_manual_pct_is_subjective',
      'all_steps_zero_weight',
    ];
    for (const k of keys) {
      expect(EVM_WARNING_DEFAULTS[k]).toBeTruthy();
    }
  });
});

describe('PERCENT_TYPES', () => {
  it('lists the three types in canonical UI order', () => {
    expect(PERCENT_TYPES).toEqual(['duration', 'units', 'physical']);
  });
});
