// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Tests for the pure, DB-free helpers behind the norm-expansion feature.
import { describe, expect, it } from 'vitest';
import {
  buildExpandBatchPayload,
  isValidQuantity,
  buildBuildAssemblyPayload,
  resourceBadge,
  withCurrency,
} from './api';

describe('isValidQuantity', () => {
  it('accepts finite positive numbers', () => {
    expect(isValidQuantity('1')).toBe(true);
    expect(isValidQuantity('12.5')).toBe(true);
    expect(isValidQuantity('0.0001')).toBe(true);
  });

  it('trims surrounding whitespace before parsing', () => {
    expect(isValidQuantity('  3  ')).toBe(true);
  });

  it('rejects blank, zero and negative quantities', () => {
    expect(isValidQuantity('')).toBe(false);
    expect(isValidQuantity('   ')).toBe(false);
    expect(isValidQuantity('0')).toBe(false);
    expect(isValidQuantity('-1')).toBe(false);
  });

  it('rejects non-numeric and non-finite input', () => {
    expect(isValidQuantity('abc')).toBe(false);
    expect(isValidQuantity('Infinity')).toBe(false);
    expect(isValidQuantity('NaN')).toBe(false);
  });
});

describe('buildExpandBatchPayload', () => {
  it('keeps valid rows and trims the work key', () => {
    const payload = buildExpandBatchPayload([
      { work_key: '  plastering_internal  ', quantity: '10' },
      { work_key: 'concrete_c30_37', quantity: '2.5' },
    ]);
    expect(payload.items).toEqual([
      { work_key: 'plastering_internal', quantity: '10' },
      { work_key: 'concrete_c30_37', quantity: '2.5' },
    ]);
  });

  it('drops rows with a blank work key or an invalid quantity', () => {
    const payload = buildExpandBatchPayload([
      { work_key: '', quantity: '10' },
      { work_key: 'formwork_wall', quantity: '0' },
      { work_key: 'formwork_wall', quantity: 'abc' },
      { work_key: 'formwork_wall', quantity: '3' },
    ]);
    expect(payload.items).toEqual([{ work_key: 'formwork_wall', quantity: '3' }]);
  });

  it('passes the quantity string through verbatim to preserve precision', () => {
    const payload = buildExpandBatchPayload([{ work_key: 'x', quantity: ' 12.5000 ' }]);
    // Trimmed, but never re-parsed into a float that could drop trailing zeros.
    expect(payload.items[0]?.quantity).toBe('12.5000');
  });

  it('returns an empty item list for empty input', () => {
    expect(buildExpandBatchPayload([])).toEqual({ items: [] });
  });
});

describe('buildBuildAssemblyPayload', () => {
  it('always sends apply_waste and omits every empty optional', () => {
    expect(
      buildBuildAssemblyPayload({
        laborRateTemplateId: '',
        machineRateTemplateId: '',
        region: '',
        applyWaste: true,
      }),
    ).toEqual({ apply_waste: true });
  });

  it('includes and trims the non-empty fields, echoing the toggle state', () => {
    expect(
      buildBuildAssemblyPayload({
        laborRateTemplateId: '  lab-1  ',
        machineRateTemplateId: ' mac-2 ',
        region: '  Berlin ',
        applyWaste: false,
      }),
    ).toEqual({
      apply_waste: false,
      labor_rate_template_id: 'lab-1',
      machine_rate_template_id: 'mac-2',
      region: 'Berlin',
    });
  });

  it('keeps the labour template but drops a whitespace-only machine template and region', () => {
    expect(
      buildBuildAssemblyPayload({
        laborRateTemplateId: 'lab-1',
        machineRateTemplateId: '   ',
        region: '',
        applyWaste: true,
      }),
    ).toEqual({ apply_waste: true, labor_rate_template_id: 'lab-1' });
  });
});

describe('resourceBadge', () => {
  it('maps the canonical resource tokens to a letter and tint', () => {
    expect(resourceBadge('labor')).toEqual({ letter: 'L', variant: 'blue', kind: 'labor' });
    expect(resourceBadge('equipment')).toEqual({
      letter: 'E',
      variant: 'warning',
      kind: 'equipment',
    });
    expect(resourceBadge('material')).toEqual({
      letter: 'M',
      variant: 'success',
      kind: 'material',
    });
  });

  it('is case-insensitive and tolerates surrounding whitespace', () => {
    expect(resourceBadge('  MATERIAL ').kind).toBe('material');
    expect(resourceBadge('Labor').letter).toBe('L');
  });

  it('falls back to a neutral marker for unknown, null or missing types', () => {
    expect(resourceBadge('subcontractor')).toEqual({
      letter: '?',
      variant: 'neutral',
      kind: 'other',
    });
    expect(resourceBadge(null)).toEqual({ letter: '?', variant: 'neutral', kind: 'other' });
    expect(resourceBadge(undefined)).toEqual({ letter: '?', variant: 'neutral', kind: 'other' });
  });
});

describe('withCurrency', () => {
  it('appends a present currency label after the verbatim value', () => {
    expect(withCurrency('47.8365', 'EUR')).toBe('47.8365 EUR');
  });

  it('renders the value verbatim, preserving trailing zeros (never re-parsed)', () => {
    expect(withCurrency('12.5000', 'USD')).toBe('12.5000 USD');
    expect(withCurrency('0.0000', '')).toBe('0.0000');
  });

  it('returns the bare value for a blank, null or undefined currency', () => {
    expect(withCurrency('900.00')).toBe('900.00');
    expect(withCurrency('900.00', null)).toBe('900.00');
    expect(withCurrency('900.00', '   ')).toBe('900.00');
  });

  it('trims surrounding whitespace on the currency code', () => {
    expect(withCurrency('5', '  GBP ')).toBe('5 GBP');
  });
});
