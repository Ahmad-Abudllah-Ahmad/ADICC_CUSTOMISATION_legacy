// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
import { describe, expect, it } from 'vitest';
import { fmtMoney, pct, signedPct } from './parts';

describe('cost-explorer money formatting', () => {
  it('appends a currency and groups the number', () => {
    const out = fmtMoney('1234.5', 'EUR');
    expect(out).toContain('EUR');
    expect(out).toMatch(/1.?234/);
  });

  it('handles empty, null and non-numeric input safely', () => {
    expect(fmtMoney('', 'EUR')).toBe('- EUR');
    expect(fmtMoney(null)).toBe('-');
    expect(fmtMoney(undefined)).toBe('-');
    expect(fmtMoney('abc')).toBe('abc');
  });

  it('accepts a plain number', () => {
    expect(fmtMoney(0)).toBe('0');
  });
});

describe('cost-explorer percentages', () => {
  it('renders a 0..1 fraction as a whole percent', () => {
    expect(pct(0)).toBe('0%');
    expect(pct(0.5)).toBe('50%');
    expect(pct(1)).toBe('100%');
    expect(pct(0.333)).toBe('33%');
  });

  it('signs an already-percent value', () => {
    expect(signedPct(-10)).toBe('-10%');
    expect(signedPct(5)).toBe('+5%');
    expect(signedPct(0)).toBe('0%');
    expect(signedPct(2.34)).toBe('+2.3%');
  });
});
