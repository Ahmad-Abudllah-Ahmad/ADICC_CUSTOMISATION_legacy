// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
import { describe, expect, it } from 'vitest';
import {
  buildInsertRow,
  distinctCurrencies,
  lowestPriceIndex,
  scopeSteps,
  topItems,
} from './analogRates';

describe('analog rates: clipboard row', () => {
  it('joins the key rate fields with tabs, description first-normalized', () => {
    const row = buildInsertRow({
      code: 'CW-100',
      description: '  Reinforced concrete wall\n C30/37  ',
      unit: 'm3',
      rate: 123.45,
      currency: 'EUR',
    });
    expect(row).toBe('CW-100\tReinforced concrete wall C30/37\tm3\t123.45\tEUR');
    // Exactly five tab-separated columns.
    expect(row.split('\t')).toHaveLength(5);
  });

  it('accepts a decimal-string rate and leaves a blank currency empty', () => {
    expect(buildInsertRow({ code: 'A', description: 'x', unit: 'm', rate: '10.5' })).toBe(
      'A\tx\tm\t10.5\t',
    );
  });

  it('never emits NaN for a missing or non-numeric rate', () => {
    expect(buildInsertRow({ code: 'A', rate: null }).split('\t')[3]).toBe('');
    expect(buildInsertRow({ code: 'A', rate: 'abc' }).split('\t')[3]).toBe('');
    expect(buildInsertRow({ code: 'A' }).split('\t')[3]).toBe('');
  });
});

describe('analog rates: currency mix', () => {
  it('collects distinct, trimmed, non-empty currencies', () => {
    expect(distinctCurrencies([{ currency: 'EUR' }, { currency: 'EUR' }, { currency: ' USD ' }])).toEqual([
      'EUR',
      'USD',
    ]);
    expect(distinctCurrencies([{ currency: '' }, { currency: null }, {}])).toEqual([]);
  });
});

describe('analog rates: cheapest candidate', () => {
  it('returns the index of the lowest strictly-positive rate', () => {
    expect(lowestPriceIndex([{ rate: 30 }, { rate: 10 }, { rate: 20 }])).toBe(1);
  });

  it('ignores zero, negative, and non-finite rates', () => {
    expect(lowestPriceIndex([{ rate: 0 }, { rate: -5 }, { rate: 42 }])).toBe(2);
    expect(lowestPriceIndex([{ rate: Number.NaN }, { rate: 'x' }])).toBe(-1);
    expect(lowestPriceIndex([])).toBe(-1);
  });

  it('parses decimal-string rates', () => {
    expect(lowestPriceIndex([{ rate: '9.99' }, { rate: '9.98' }])).toBe(1);
  });
});

describe('analog rates: capped lists', () => {
  it('slices to n and reports how many were dropped', () => {
    const { shown, more } = topItems([1, 2, 3, 4, 5, 6], 4);
    expect(shown).toEqual([1, 2, 3, 4]);
    expect(more).toBe(2);
  });

  it('is null-safe and filters holes', () => {
    expect(topItems(undefined, 3)).toEqual({ shown: [], more: 0 });
    expect(topItems([1, null, 2], 4).shown).toEqual([1, 2]);
  });
});

describe('analog rates: application conditions', () => {
  it('reads scope_of_work steps, trims, and caps', () => {
    const item = { metadata_: { scope_of_work: [' Excavate ', 'Formwork', 'Pour', 'Cure'] } };
    const { shown, more } = scopeSteps(item, 3);
    expect(shown).toEqual(['Excavate', 'Formwork', 'Pour']);
    expect(more).toBe(1);
  });

  it('drops non-string / blank steps and tolerates missing metadata', () => {
    expect(scopeSteps({ metadata_: { scope_of_work: ['ok', '', 2, null] } }, 5).shown).toEqual(['ok']);
    expect(scopeSteps({ metadata_: null }).shown).toEqual([]);
    expect(scopeSteps(undefined).shown).toEqual([]);
    expect(scopeSteps({}).more).toBe(0);
  });
});
