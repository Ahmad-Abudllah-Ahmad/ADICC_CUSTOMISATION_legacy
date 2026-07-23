// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';
import {
  CHANGE_VARIANT,
  filterCompareRows,
  toFiniteOrNull,
  deltaSign,
  showsPair,
} from './compareHelpers';
import type { ComparePositionRow } from './api';

function row(over: Partial<ComparePositionRow> = {}): ComparePositionRow {
  return {
    change_type: 'unchanged',
    match_key: 'rc:R-1',
    reference_code: 'R-1',
    ordinal: '01',
    description: 'Line',
    unit: 'm3',
    old_quantity: '10',
    new_quantity: '10',
    old_unit_rate: '100',
    new_unit_rate: '100',
    old_total: '1000',
    new_total: '1000',
    old_total_base: '1000',
    new_total_base: '1000',
    currency: 'EUR',
    total_delta_base: '0',
    ...over,
  };
}

describe('CHANGE_VARIANT', () => {
  it('maps every change type to a stable badge variant', () => {
    expect(CHANGE_VARIANT.added).toBe('success');
    expect(CHANGE_VARIANT.removed).toBe('error');
    expect(CHANGE_VARIANT.qty_changed).toBe('warning');
    expect(CHANGE_VARIANT.rate_changed).toBe('warning');
    expect(CHANGE_VARIANT.changed).toBe('warning');
    expect(CHANGE_VARIANT.unchanged).toBe('neutral');
  });
});

describe('filterCompareRows', () => {
  const rows = [
    row({ change_type: 'unchanged', match_key: 'a' }),
    row({ change_type: 'qty_changed', match_key: 'b' }),
    row({ change_type: 'added', match_key: 'c' }),
    row({ change_type: 'removed', match_key: 'd' }),
  ];

  it('keeps every row when hideUnchanged is false', () => {
    expect(filterCompareRows(rows, false)).toHaveLength(4);
  });

  it('drops only unchanged rows when hideUnchanged is true', () => {
    const out = filterCompareRows(rows, true);
    expect(out.map((r) => r.match_key)).toEqual(['b', 'c', 'd']);
    expect(out.some((r) => r.change_type === 'unchanged')).toBe(false);
  });

  it('never hides added/removed lines', () => {
    const out = filterCompareRows(
      [row({ change_type: 'added' }), row({ change_type: 'removed' })],
      true,
    );
    expect(out).toHaveLength(2);
  });
});

describe('toFiniteOrNull', () => {
  it('parses an exact decimal string into a number', () => {
    expect(toFiniteOrNull('1234.5600')).toBe(1234.56);
  });
  it('returns null for empty / nullish / non-finite', () => {
    expect(toFiniteOrNull('')).toBeNull();
    expect(toFiniteOrNull(null)).toBeNull();
    expect(toFiniteOrNull(undefined)).toBeNull();
    expect(toFiniteOrNull('not-a-number')).toBeNull();
  });
});

describe('deltaSign', () => {
  it('returns the sign of a base-currency delta string', () => {
    expect(deltaSign('900.00')).toBe(1);
    expect(deltaSign('-50')).toBe(-1);
    expect(deltaSign('0')).toBe(0);
    expect(deltaSign(null)).toBe(0);
    expect(deltaSign('')).toBe(0);
  });
});

describe('showsPair', () => {
  it('shows a qty pair only when the quantity moved', () => {
    expect(showsPair('qty_changed', 'qty')).toBe(true);
    expect(showsPair('changed', 'qty')).toBe(true);
    expect(showsPair('rate_changed', 'qty')).toBe(false);
    expect(showsPair('added', 'qty')).toBe(false);
    expect(showsPair('unchanged', 'qty')).toBe(false);
  });

  it('shows a rate pair only when the rate moved', () => {
    expect(showsPair('rate_changed', 'rate')).toBe(true);
    expect(showsPair('changed', 'rate')).toBe(true);
    expect(showsPair('qty_changed', 'rate')).toBe(false);
    expect(showsPair('removed', 'rate')).toBe(false);
  });
});
