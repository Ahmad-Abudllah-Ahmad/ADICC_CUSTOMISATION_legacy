// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
import { describe, expect, it } from 'vitest';
import {
  buildBuyListCsv,
  buyListCsvName,
  isEmptyBuyList,
  isEmptyStatement,
  kindAccentClass,
  resourceStatementCsvName,
  statementCurrency,
  type MaterialBuyListItem,
} from './api';

describe('resourceStatementCsvName', () => {
  it('builds a stable, safe filename from a project id', () => {
    const name = resourceStatementCsvName('3fa85f64-5717-4562-b3fc-2c963f66afa6');
    expect(name.startsWith('resource-statement-')).toBe(true);
    expect(name.endsWith('.csv')).toBe(true);
  });

  it('strips unsafe path characters', () => {
    const name = resourceStatementCsvName('abc/../../x');
    expect(name).not.toContain('/');
    expect(name).not.toContain('..');
    expect(name).toBe('resource-statement-abcx.csv');
  });

  it('falls back to a placeholder for an empty id', () => {
    expect(resourceStatementCsvName('')).toBe('resource-statement-project.csv');
  });
});

describe('isEmptyStatement', () => {
  it('treats null / missing groups as empty', () => {
    expect(isEmptyStatement(null)).toBe(true);
    expect(isEmptyStatement(undefined)).toBe(true);
    expect(isEmptyStatement({ groups: [] })).toBe(true);
  });

  it('treats groups whose lines are all empty as empty', () => {
    expect(
      isEmptyStatement({
        groups: [
          { kind: 'labor', kind_i18n_key: '', label: '', line_count: 0, total_cost: '0', total_hours: null, lines: [] },
        ],
      }),
    ).toBe(true);
  });

  it('is not empty when a group carries a line', () => {
    expect(
      isEmptyStatement({
        groups: [
          {
            kind: 'material',
            kind_i18n_key: '',
            label: '',
            line_count: 1,
            total_cost: '10',
            total_hours: null,
            lines: [{ kind: 'material', kind_i18n_key: '', name: 'Brick', unit: 'pcs', quantity: '10', cost: '10', position_count: 1 }],
          },
        ],
      }),
    ).toBe(false);
  });
});

describe('statementCurrency', () => {
  it('returns a set currency code', () => {
    expect(statementCurrency({ currency: 'EUR' })).toBe('EUR');
  });

  it('returns undefined for an unset or blank currency', () => {
    expect(statementCurrency({ currency: '' })).toBeUndefined();
    expect(statementCurrency({ currency: '   ' })).toBeUndefined();
    expect(statementCurrency(null)).toBeUndefined();
  });
});

describe('kindAccentClass', () => {
  it('maps known kinds to accent classes', () => {
    expect(kindAccentClass('labor')).toContain('oe-blue');
    expect(kindAccentClass('material')).toContain('success');
    expect(kindAccentClass('machinery')).toContain('warning');
  });

  it('falls back to a neutral class for an unknown kind', () => {
    expect(kindAccentClass('mystery')).toBe('text-content-tertiary');
  });
});

describe('buyListCsvName', () => {
  it('builds a stable, safe filename from a project id', () => {
    const name = buyListCsvName('3fa85f64-5717-4562-b3fc-2c963f66afa6');
    expect(name.startsWith('material-buy-list-')).toBe(true);
    expect(name.endsWith('.csv')).toBe(true);
  });

  it('strips unsafe path characters and falls back for an empty id', () => {
    expect(buyListCsvName('abc/../../x')).toBe('material-buy-list-abcx.csv');
    expect(buyListCsvName('')).toBe('material-buy-list-project.csv');
  });
});

describe('isEmptyBuyList', () => {
  it('treats null / missing / empty items as empty', () => {
    expect(isEmptyBuyList(null)).toBe(true);
    expect(isEmptyBuyList(undefined)).toBe(true);
    expect(isEmptyBuyList({ items: [] })).toBe(true);
  });

  it('is not empty when at least one item is present', () => {
    const item: MaterialBuyListItem = {
      name: 'Brick',
      unit: 'pcs',
      quantity: '10',
      cost: '10',
      position_count: 1,
      currency: 'EUR',
    };
    expect(isEmptyBuyList({ items: [item] })).toBe(false);
  });
});

describe('buildBuyListCsv', () => {
  const items: MaterialBuyListItem[] = [
    { name: 'Concrete C30/37', unit: 'm3', quantity: '71.4000', cost: '6783.00', position_count: 2, currency: 'EUR' },
    { name: 'Bolt, M12, galvanised', unit: 'pcs', quantity: '100.0000', cost: '210.00', position_count: 1, currency: 'EUR' },
  ];

  it('writes a header row and one row per material', () => {
    const csv = buildBuyListCsv(items, 'EUR');
    const rows = csv.split('\r\n');
    expect(rows).toHaveLength(3);
    expect(rows[0]).toBe('Material,Unit,Quantity,Estimated cost,Currency,Used in positions');
  });

  it('prints the money and quantity strings verbatim (no float math)', () => {
    const csv = buildBuyListCsv(items, 'EUR');
    expect(csv).toContain('m3,71.4000,6783.00,EUR,2');
  });

  it('escapes a comma-bearing material name so it stays one field', () => {
    const csv = buildBuyListCsv(items, 'EUR');
    expect(csv).toContain('"Bolt, M12, galvanised"');
  });

  it('tolerates an undefined currency', () => {
    const csv = buildBuyListCsv([{ ...items[0]! }], undefined);
    // Currency column is blank but the row shape is intact.
    expect(csv).toContain('Concrete C30/37,m3,71.4000,6783.00,,2');
  });

  it('produces just the header for an empty list', () => {
    const csv = buildBuyListCsv([], 'EUR');
    expect(csv).toBe('Material,Unit,Quantity,Estimated cost,Currency,Used in positions');
  });
});
