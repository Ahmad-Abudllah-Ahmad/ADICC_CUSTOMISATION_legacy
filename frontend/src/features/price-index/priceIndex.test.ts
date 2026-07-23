// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
// Unit tests for the pure price-index helpers. No DOM / network needed - these
// exercise the string/number helpers the page relies on for validation and
// display, keeping money and factors as exact strings (never float math).
import { describe, it, expect } from 'vitest';

import {
  isValidPeriod,
  formatFactor,
  factorDirection,
  blankAdjustLine,
  isAdjustLineReady,
  isValidIsoDate,
  hasEscalateSelector,
} from './api';

describe('isValidPeriod', () => {
  it('accepts a well-formed ISO year-month', () => {
    expect(isValidPeriod('2026-01')).toBe(true);
    expect(isValidPeriod('1999-12')).toBe(true);
    expect(isValidPeriod(' 2026-06 ')).toBe(true); // trimmed
  });

  it('rejects a bad month, short year or wrong separator', () => {
    expect(isValidPeriod('2026-13')).toBe(false);
    expect(isValidPeriod('2026-00')).toBe(false);
    expect(isValidPeriod('2026-1')).toBe(false);
    expect(isValidPeriod('26-01')).toBe(false);
    expect(isValidPeriod('2026/01')).toBe(false);
  });

  it('treats empty / null / undefined as invalid', () => {
    expect(isValidPeriod('')).toBe(false);
    expect(isValidPeriod(null)).toBe(false);
    expect(isValidPeriod(undefined)).toBe(false);
  });
});

describe('formatFactor', () => {
  it('trims trailing zeros without float math', () => {
    expect(formatFactor('1.400000')).toBe('1.4');
    expect(formatFactor('1.000000')).toBe('1');
    expect(formatFactor('0.900000')).toBe('0.9');
    expect(formatFactor('1.010000')).toBe('1.01');
    expect(formatFactor('0.000000')).toBe('0');
  });

  it('keeps a value that needs all its digits', () => {
    expect(formatFactor('1.277778')).toBe('1.277778');
  });

  it('passes an integer string straight through', () => {
    expect(formatFactor('5')).toBe('5');
    expect(formatFactor('10')).toBe('10');
  });

  it('returns an empty string for null / empty input', () => {
    expect(formatFactor('')).toBe('');
    expect(formatFactor(null)).toBe('');
    expect(formatFactor(undefined)).toBe('');
  });
});

describe('factorDirection', () => {
  it('classifies above / below / equal to one', () => {
    expect(factorDirection('1.4')).toBe('up');
    expect(factorDirection('2')).toBe('up');
    expect(factorDirection('0.9')).toBe('down');
    expect(factorDirection('0.5')).toBe('down');
    expect(factorDirection('1')).toBe('flat');
    expect(factorDirection('1.000000')).toBe('flat');
  });

  it('treats missing / unparseable input as flat', () => {
    expect(factorDirection('')).toBe('flat');
    expect(factorDirection(null)).toBe('flat');
    expect(factorDirection('not-a-number')).toBe('flat');
  });
});

describe('blankAdjustLine', () => {
  it('returns an all-empty line', () => {
    expect(blankAdjustLine()).toEqual({
      amount: '',
      base_period: '',
      target_period: '',
      base_region: '',
      target_region: '',
    });
  });
});

describe('isAdjustLineReady', () => {
  const base = blankAdjustLine();

  it('is ready with a non-negative amount and two valid periods', () => {
    expect(
      isAdjustLineReady({ ...base, amount: '1000', base_period: '2019-01', target_period: '2026-01' }),
    ).toBe(true);
    // zero is a legal amount
    expect(
      isAdjustLineReady({ ...base, amount: '0', base_period: '2019-01', target_period: '2026-01' }),
    ).toBe(true);
  });

  it('is not ready when the amount is blank or negative', () => {
    expect(isAdjustLineReady({ ...base, base_period: '2019-01', target_period: '2026-01' })).toBe(false);
    expect(
      isAdjustLineReady({ ...base, amount: '-5', base_period: '2019-01', target_period: '2026-01' }),
    ).toBe(false);
  });

  it('is not ready when a period is missing or malformed', () => {
    expect(isAdjustLineReady({ ...base, amount: '10', base_period: '2019-01', target_period: '' })).toBe(false);
    expect(
      isAdjustLineReady({ ...base, amount: '10', base_period: '2019-13', target_period: '2026-01' }),
    ).toBe(false);
  });
});

describe('isValidIsoDate', () => {
  it('accepts a well-formed ISO calendar date', () => {
    expect(isValidIsoDate('2026-07-08')).toBe(true);
    expect(isValidIsoDate('1999-12-31')).toBe(true);
    expect(isValidIsoDate(' 2026-01-01 ')).toBe(true); // trimmed
  });

  it('rejects a bad month/day, short year or wrong separator', () => {
    expect(isValidIsoDate('2026-13-01')).toBe(false);
    expect(isValidIsoDate('2026-00-10')).toBe(false);
    expect(isValidIsoDate('2026-07-32')).toBe(false);
    expect(isValidIsoDate('2026-07-00')).toBe(false);
    expect(isValidIsoDate('2026-7-8')).toBe(false);
    expect(isValidIsoDate('2026-07')).toBe(false);
    expect(isValidIsoDate('2026/07/08')).toBe(false);
  });

  it('treats empty / null / undefined as invalid', () => {
    expect(isValidIsoDate('')).toBe(false);
    expect(isValidIsoDate(null)).toBe(false);
    expect(isValidIsoDate(undefined)).toBe(false);
  });
});

describe('hasEscalateSelector', () => {
  it('is true when a region, category, or explicit ids are set', () => {
    expect(hasEscalateSelector({ region: 'DE_BERLIN' })).toBe(true);
    expect(hasEscalateSelector({ category: 'Concrete' })).toBe(true);
    expect(hasEscalateSelector({ cost_item_ids: ['a'] })).toBe(true);
  });

  it('is false when nothing is selected (blank / whitespace / empty)', () => {
    expect(hasEscalateSelector({})).toBe(false);
    expect(hasEscalateSelector({ region: '', category: '' })).toBe(false);
    expect(hasEscalateSelector({ region: '   ', category: '  ' })).toBe(false);
    expect(hasEscalateSelector({ region: null, category: null, cost_item_ids: [] })).toBe(false);
  });
});
