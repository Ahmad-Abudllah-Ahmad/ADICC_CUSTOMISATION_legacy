// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for isGoodsReceiptFullyReceived().
//
// Regression guard for the GR-table "fully received" highlight: the wire
// quantities are Decimal STRINGS, so a raw string `>=` compared them
// lexicographically ("9" >= "100" -> true). These cases pin the numeric
// comparison.

import { describe, it, expect } from 'vitest';

import { isGoodsReceiptFullyReceived } from './ProcurementPage';

describe('isGoodsReceiptFullyReceived', () => {
  it('returns true when received exactly equals ordered', () => {
    expect(isGoodsReceiptFullyReceived('100', '100')).toBe(true);
  });

  it('returns true when received exceeds ordered (over-received)', () => {
    expect(isGoodsReceiptFullyReceived('120', '100')).toBe(true);
  });

  it('returns false when received is below ordered', () => {
    expect(isGoodsReceiptFullyReceived('50', '100')).toBe(false);
  });

  // The bug this fixes: lexicographic string comparison would have made
  // "9" >= "100" true, painting an under-received row green.
  it('does NOT treat a smaller multi-digit received as complete (lexicographic trap)', () => {
    expect(isGoodsReceiptFullyReceived('9', '100')).toBe(false);
  });

  // The inverse lexicographic trap: "100" >= "20" is false as strings.
  it('treats 100 of 20 as fully received (inverse lexicographic trap)', () => {
    expect(isGoodsReceiptFullyReceived('100', '20')).toBe(true);
  });

  it('handles decimal quantities numerically', () => {
    expect(isGoodsReceiptFullyReceived('5.5', '5.50')).toBe(true);
    expect(isGoodsReceiptFullyReceived('5.4', '5.5')).toBe(false);
  });

  it('returns false when nothing was ordered (no empty-row highlight)', () => {
    expect(isGoodsReceiptFullyReceived('0', '0')).toBe(false);
    expect(isGoodsReceiptFullyReceived('5', '0')).toBe(false);
  });

  it('treats null/undefined quantities as zero', () => {
    expect(isGoodsReceiptFullyReceived(null, '100')).toBe(false);
    expect(isGoodsReceiptFullyReceived('100', null)).toBe(false);
    expect(isGoodsReceiptFullyReceived(undefined, undefined)).toBe(false);
  });

  it('returns false for unparseable input rather than NaN-comparing', () => {
    expect(isGoodsReceiptFullyReceived('abc', '100')).toBe(false);
    expect(isGoodsReceiptFullyReceived('100', 'xyz')).toBe(false);
  });

  it('accepts numeric inputs too (defensive)', () => {
    expect(isGoodsReceiptFullyReceived(100, 100)).toBe(true);
    expect(isGoodsReceiptFullyReceived(9, 100)).toBe(false);
  });
});
