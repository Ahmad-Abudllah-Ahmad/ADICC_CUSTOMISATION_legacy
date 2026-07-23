// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Tests for the Pivot aggregation helpers — especially the new `count` and
 * `count_unique` functions added in Q2. These run purely client-side
 * because the backend endpoint rejects `count_unique` as unknown.
 */
import { describe, it, expect } from 'vitest';
import {
  computeClientPivot,
  isNumericAggFn,
  isCategoricalAggFn,
  canAggregateColumn,
  formatCount,
  rollupParentValue,
  AGG_FUNCTIONS,
} from '@/features/cad-explorer/aggregation';
import type { AggregateGroup } from '@/features/cad-explorer/api';

/** Minimal synthetic dataset — two categories, mixed text / numeric
 *  columns, some nulls. Chosen so the expected counts are obvious by
 *  inspection. */
const rows: Record<string, unknown>[] = [
  { category: 'Wall',  client_name: 'ACME',   volume: 1.0 },
  { category: 'Wall',  client_name: 'ACME',   volume: 2.0 },
  { category: 'Wall',  client_name: 'BetaCo', volume: 3.0 },
  { category: 'Wall',  client_name: null,     volume: 4.0 },
  { category: 'Floor', client_name: 'ACME',   volume: null },
  { category: 'Floor', client_name: 'GammaLtd', volume: 5.0 },
];

describe('aggregation - AGG_FUNCTIONS vocabulary', () => {
  it('includes all six supported functions', () => {
    expect(AGG_FUNCTIONS).toContain('sum');
    expect(AGG_FUNCTIONS).toContain('avg');
    expect(AGG_FUNCTIONS).toContain('min');
    expect(AGG_FUNCTIONS).toContain('max');
    expect(AGG_FUNCTIONS).toContain('count');
    expect(AGG_FUNCTIONS).toContain('count_unique');
  });
});

describe('aggregation - validators', () => {
  it('isNumericAggFn returns true only for numeric aggs', () => {
    expect(isNumericAggFn('sum')).toBe(true);
    expect(isNumericAggFn('avg')).toBe(true);
    expect(isNumericAggFn('min')).toBe(true);
    expect(isNumericAggFn('max')).toBe(true);
    expect(isNumericAggFn('count')).toBe(false);
    expect(isNumericAggFn('count_unique')).toBe(false);
    expect(isNumericAggFn('bogus')).toBe(false);
  });

  it('isCategoricalAggFn returns true only for count / count_unique', () => {
    expect(isCategoricalAggFn('count')).toBe(true);
    expect(isCategoricalAggFn('count_unique')).toBe(true);
    expect(isCategoricalAggFn('sum')).toBe(false);
    expect(isCategoricalAggFn('avg')).toBe(false);
    expect(isCategoricalAggFn('bogus')).toBe(false);
  });

  it('canAggregateColumn - sum rejects text columns', () => {
    expect(canAggregateColumn('sum', false)).toBe(false);
    expect(canAggregateColumn('sum', true)).toBe(true);
    expect(canAggregateColumn('avg', false)).toBe(false);
    expect(canAggregateColumn('min', false)).toBe(false);
    expect(canAggregateColumn('max', false)).toBe(false);
  });

  it('canAggregateColumn - count / count_unique accept any dtype', () => {
    expect(canAggregateColumn('count', false)).toBe(true);
    expect(canAggregateColumn('count', true)).toBe(true);
    expect(canAggregateColumn('count_unique', false)).toBe(true);
    expect(canAggregateColumn('count_unique', true)).toBe(true);
  });
});

describe('aggregation - computeClientPivot (count)', () => {
  it('returns non-null row count per group for a text column', () => {
    const result = computeClientPivot(rows, ['category'], ['client_name'], 'count');
    expect(result.groups).toHaveLength(2);
    const wall = result.groups.find((g) => g.key.category === 'Wall');
    const floor = result.groups.find((g) => g.key.category === 'Floor');
    // Wall: 4 rows total, 3 have non-null client_name
    expect(wall?.results.client_name).toBe(3);
    expect(wall?.count).toBe(4);
    // Floor: 2 rows, both have client_name
    expect(floor?.results.client_name).toBe(2);
    expect(floor?.count).toBe(2);
  });

  it('totals.count sums non-null rows across the whole dataset', () => {
    const result = computeClientPivot(rows, ['category'], ['client_name'], 'count');
    expect(result.totals.client_name).toBe(5); // 3 + 2
    expect(result.total_count).toBe(6);
  });

  it('works on a numeric column (counts non-null numeric rows)', () => {
    const result = computeClientPivot(rows, ['category'], ['volume'], 'count');
    const wall = result.groups.find((g) => g.key.category === 'Wall');
    const floor = result.groups.find((g) => g.key.category === 'Floor');
    expect(wall?.results.volume).toBe(4); // all 4 Walls have volume
    expect(floor?.results.volume).toBe(1); // only 1 Floor has volume
  });

  it('handles multiple aggCols simultaneously', () => {
    const result = computeClientPivot(
      rows,
      ['category'],
      ['client_name', 'volume'],
      'count',
    );
    const wall = result.groups.find((g) => g.key.category === 'Wall');
    expect(wall?.results.client_name).toBe(3);
    expect(wall?.results.volume).toBe(4);
  });
});

describe('aggregation - computeClientPivot (count_unique)', () => {
  it('returns distinct non-null value count per group', () => {
    const result = computeClientPivot(
      rows,
      ['category'],
      ['client_name'],
      'count_unique',
    );
    const wall = result.groups.find((g) => g.key.category === 'Wall');
    const floor = result.groups.find((g) => g.key.category === 'Floor');
    // Wall clients: ACME, ACME, BetaCo, null → 2 distinct
    expect(wall?.results.client_name).toBe(2);
    // Floor clients: ACME, GammaLtd → 2 distinct
    expect(floor?.results.client_name).toBe(2);
  });

  it('totals.count_unique aggregates distinct values across the whole dataset', () => {
    const result = computeClientPivot(
      rows,
      ['category'],
      ['client_name'],
      'count_unique',
    );
    // Across both groups: ACME, BetaCo, GammaLtd → 3 distinct
    expect(result.totals.client_name).toBe(3);
  });

  it('treats empty strings as null for distinct counting', () => {
    const withEmpties: Record<string, unknown>[] = [
      { category: 'A', name: 'x' },
      { category: 'A', name: '' },
      { category: 'A', name: 'x' }, // duplicate
      { category: 'A', name: null },
    ];
    const result = computeClientPivot(
      withEmpties,
      ['category'],
      ['name'],
      'count_unique',
    );
    expect(result.groups[0]!.results.name).toBe(1); // just 'x'
  });

  it('produces deterministic group ordering (alphabetical by first group-by)', () => {
    const result = computeClientPivot(
      rows,
      ['category'],
      ['client_name'],
      'count_unique',
    );
    expect(result.groups.map((g) => g.key.category)).toEqual(['Floor', 'Wall']);
  });

  it('returns zero-distinct groups cleanly', () => {
    const allNull: Record<string, unknown>[] = [
      { category: 'Z', thing: null },
      { category: 'Z', thing: null },
    ];
    const result = computeClientPivot(allNull, ['category'], ['thing'], 'count_unique');
    expect(result.groups[0]!.results.thing).toBe(0);
  });
});

describe('aggregation - formatCount', () => {
  it('formats integers with locale separators', () => {
    const s = formatCount(1234);
    // Any locale's grouping separator between 1 and 234 is acceptable.
    expect(s).toMatch(/1[^0-9]234/);
  });

  it('rounds fractional inputs to the nearest integer', () => {
    expect(formatCount(1.4).replace(/[^0-9-]/g, '')).toBe('1');
    expect(formatCount(1.6).replace(/[^0-9-]/g, '')).toBe('2');
  });

  it('returns placeholder for null / undefined / NaN / Infinity', () => {
    expect(formatCount(null)).toBe('-');
    expect(formatCount(undefined)).toBe('-');
    expect(formatCount(NaN)).toBe('-');
    expect(formatCount(Infinity)).toBe('-');
  });

  it('never includes a decimal point', () => {
    expect(formatCount(42)).not.toMatch(/[.,]\d/);
  });
});

/**
 * D-TKC-008: hierarchical pivot parent rows must roll up with the SAME
 * aggregation the user picked, not an unconditional sum of child
 * results. Previously aggFn='avg' showed Σ(child averages).
 */
describe('aggregation - rollupParentValue', () => {
  // Two child groups: 4 elements averaging 2.0, 6 elements averaging 3.0.
  const children: AggregateGroup[] = [
    { key: { type: 'A' }, results: { x: 2 }, count: 4 },
    { key: { type: 'B' }, results: { x: 3 }, count: 6 },
  ];

  it('sum / count are additive', () => {
    expect(rollupParentValue(children, 'x', 'sum')).toBe(5);
    expect(rollupParentValue(children, 'x', 'count')).toBe(5);
  });

  it('avg is the count-weighted mean (not the sum of averages)', () => {
    // (2*4 + 3*6) / (4+6) = 26/10 = 2.6 — NOT 5 (the old bug).
    expect(rollupParentValue(children, 'x', 'avg')).toBeCloseTo(2.6, 9);
  });

  it('min is the min of child mins, max the max of child maxes', () => {
    expect(rollupParentValue(children, 'x', 'min')).toBe(2);
    expect(rollupParentValue(children, 'x', 'max')).toBe(3);
  });

  it('count_unique is not derivable from group summaries → null', () => {
    expect(rollupParentValue(children, 'x', 'count_unique')).toBeNull();
  });

  it('empty children rolls up to 0', () => {
    expect(rollupParentValue([], 'x', 'avg')).toBe(0);
  });

  it('avg with zero total count does not divide by zero', () => {
    const zero: AggregateGroup[] = [{ key: {}, results: { x: 9 }, count: 0 }];
    expect(rollupParentValue(zero, 'x', 'avg')).toBe(0);
  });
});
