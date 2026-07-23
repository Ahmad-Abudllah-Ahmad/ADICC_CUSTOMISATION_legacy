/**
 * Unit tests for the money primitives (`toNum`, `formatCurrency`).
 *
 * The contract under test is the Decimal-as-string backend money format:
 * `toNum` must accept the string the wire actually delivers without ever
 * yielding NaN/Infinity, and `formatCurrency` must coerce safely, never
 * fall back to a wrong currency symbol, and honour fraction overrides.
 *
 * `locale` is passed explicitly so the assertions are independent of the
 * test runner's i18next/browser locale.
 */
import { describe, it, expect } from 'vitest';
import { toNum, formatCurrency } from './money';

describe('toNum', () => {
  it('passes through finite numbers', () => {
    expect(toNum(1234.56)).toBe(1234.56);
    expect(toNum(0)).toBe(0);
    expect(toNum(-42)).toBe(-42);
  });

  it('parses the Decimal-as-string backend format', () => {
    expect(toNum('1234.56')).toBe(1234.56);
    expect(toNum('0')).toBe(0);
    expect(toNum('-42.5')).toBe(-42.5);
  });

  it('collapses null / undefined / empty to 0', () => {
    expect(toNum(null)).toBe(0);
    expect(toNum(undefined)).toBe(0);
    expect(toNum('')).toBe(0);
  });

  it('collapses unparseable / non-finite input to 0 (never NaN)', () => {
    expect(toNum('not a number')).toBe(0);
    expect(toNum(NaN)).toBe(0);
    expect(toNum(Infinity)).toBe(0);
    expect(toNum(-Infinity)).toBe(0);
    expect(Number.isNaN(toNum('abc'))).toBe(false);
  });

  it('does not throw on a string (the historical .toFixed crash class)', () => {
    // The whole reason this helper exists: code used to call .toFixed on a
    // string and crash. toNum makes the value safe to .toFixed afterwards.
    expect(() => toNum('99.99').toFixed(2)).not.toThrow();
    expect(toNum('99.99').toFixed(2)).toBe('99.99');
  });
});

describe('formatCurrency', () => {
  it('formats a Decimal-string with the currency symbol', () => {
    // Use a non-breaking-space-tolerant check: assert the digits + symbol
    // are present rather than pinning exact whitespace (Intl uses NBSP).
    const out = formatCurrency('1234.56', 'USD', 'en-US');
    expect(out).toContain('$');
    expect(out).toContain('1,234.56');
  });

  it('uses the currency natural minor units by default', () => {
    // JPY has 0 minor units; KWD has 3.
    expect(formatCurrency('1000', 'JPY', 'en-US')).toContain('1,000');
    expect(formatCurrency('1000', 'JPY', 'en-US')).not.toContain('.00');
    expect(formatCurrency('1.5', 'KWD', 'en-US')).toContain('1.500');
  });

  it('renders a plain grouped number (no symbol) for unknown currency', () => {
    const out = formatCurrency('1234.56', '', 'en-US');
    expect(out).toBe('1,234.56'); // 2 fraction digits, no symbol
    expect(out).not.toContain('€');
    expect(out).not.toContain('$');
  });

  it('never falls back to EUR for a blank / invalid code', () => {
    expect(formatCurrency('1000', undefined, 'en-US')).not.toContain('€');
    expect(formatCurrency('1000', 'xx', 'en-US')).not.toContain('€');
    expect(formatCurrency('1000', '123', 'en-US')).not.toContain('€');
  });

  it('honours fraction-digit overrides (whole-number summaries)', () => {
    const whole = formatCurrency('1234.56', 'USD', 'en-US', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    });
    expect(whole).toContain('$');
    expect(whole).toContain('1,235'); // rounded, no cents
    expect(whole).not.toContain('.56');
  });

  it('coerces null / undefined / NaN to a formatted zero, never crashes', () => {
    expect(() => formatCurrency(null, 'USD', 'en-US')).not.toThrow();
    expect(formatCurrency(null, 'USD', 'en-US')).toContain('0');
    expect(formatCurrency(undefined, '', 'en-US')).toBe('0.00');
    expect(formatCurrency('garbage', 'USD', 'en-US')).toContain('0');
  });

  it('accepts a genuine number as well as a string', () => {
    expect(formatCurrency(1234.56, 'USD', 'en-US')).toContain('1,234.56');
  });
});
