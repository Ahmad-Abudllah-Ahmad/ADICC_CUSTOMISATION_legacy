// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Tests for the feet-and-inches parser (Issue #290).
 *
 * US estimators enter dimensions as feet-and-inches (10'6"). Before the fix
 * these committed as `parseFloat || 0`, silently truncating (10'6" -> 10,
 * 3/4" -> 3, glyph fractions -> 0). `parseFeetInches` returns DECIMAL FEET
 * for genuine ft-in notation and `null` for anything else (a bare number or a
 * real formula) so it never misreads non-ft-in input.
 */

import { describe, it, expect } from 'vitest';
import { parseFeetInches } from './cellEditors';

describe('parseFeetInches - feet + inches', () => {
  it('parses feet and whole inches', () => {
    expect(parseFeetInches('10\'6"')).toBe(10.5);
    expect(parseFeetInches('10\' 6"')).toBe(10.5);
    expect(parseFeetInches('10\'-6"')).toBe(10.5); // architectural dash form
    expect(parseFeetInches('10\'  6"')).toBe(10.5); // multiple spaces
  });

  it('parses feet only', () => {
    expect(parseFeetInches('10\'')).toBe(10);
  });

  it('parses inches only', () => {
    expect(parseFeetInches('6"')).toBe(0.5);
  });
});

describe('parseFeetInches - fractional inches', () => {
  it('parses a bare fraction as inches', () => {
    expect(parseFeetInches('3/4"')).toBeCloseTo(0.0625, 10); // 0.75 in / 12
    expect(parseFeetInches('11/16"')).toBeCloseTo(11 / 16 / 12, 10);
  });

  it('parses feet plus a fractional inch', () => {
    expect(parseFeetInches('10\'  3/4"')).toBeCloseTo(10.0625, 10);
  });

  it('parses a whole-plus-fraction inch', () => {
    expect(parseFeetInches('6 3/4"')).toBeCloseTo(6.75 / 12, 10);
  });

  it('maps vulgar-fraction glyphs to their value', () => {
    expect(parseFeetInches('¾"')).toBeCloseTo(0.0625, 10); // ¾" -> 0.75 in
    expect(parseFeetInches('½"')).toBeCloseTo(0.5 / 12, 10); // ½"
    expect(parseFeetInches('10\'¼"')).toBeCloseTo(10 + 0.25 / 12, 10); // 10'¼"
  });
});

describe('parseFeetInches - smart quotes and primes', () => {
  it('accepts prime / smart-quote marks', () => {
    expect(parseFeetInches('10′ 6″')).toBe(10.5); // 10′ 6″
    expect(parseFeetInches('10’ 6”')).toBe(10.5); // 10’ 6”
  });
});

describe('parseFeetInches - rejects non-ft-in input', () => {
  it('returns null for a bare number (no foot/inch mark)', () => {
    expect(parseFeetInches('10.5')).toBeNull();
    expect(parseFeetInches('10')).toBeNull();
    expect(parseFeetInches('')).toBeNull();
  });

  it('returns null for a real formula', () => {
    expect(parseFeetInches('=2*3')).toBeNull();
    expect(parseFeetInches('$GFA * 0.15')).toBeNull();
    expect(parseFeetInches('pos("1.1").qty')).toBeNull(); // has " but is a formula
  });

  it('returns null for negatives and zero denominators', () => {
    expect(parseFeetInches('-6"')).toBeNull();
    expect(parseFeetInches('-10\'6"')).toBeNull();
    expect(parseFeetInches('3/0"')).toBeNull();
  });

  it('returns null for garbage', () => {
    expect(parseFeetInches('abc')).toBeNull();
    expect(parseFeetInches('\'')).toBeNull(); // lone foot mark, no number
  });
});
