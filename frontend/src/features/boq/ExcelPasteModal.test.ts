// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
import { describe, it, expect } from 'vitest';
import { parseRows } from './ExcelPasteModal';

/**
 * parseRows is the pasted-clipboard parser behind the Excel paste modal.
 * These tests pin the honesty behaviour from issue #347: a cell that is not
 * a usable number, and a line without a description, must be counted and
 * reported rather than silently read as zero or dropped.
 */
describe('parseRows', () => {
  it('returns empty diagnostics for empty input', () => {
    expect(parseRows('')).toEqual({
      rows: [],
      detectedHeaders: [],
      skippedEmpty: 0,
      invalidNumbers: 0,
    });
  });

  it('detects a header row and parses the data below it', () => {
    const out = parseRows('Description\tUnit\tQty\tRate\nConcrete\tm3\t120\t185.00');
    expect(out.rows).toHaveLength(1);
    expect(out.rows[0]).toMatchObject({
      description: 'Concrete',
      unit: 'm3',
      quantity: 120,
      unit_rate: 185,
    });
    expect(out.detectedHeaders).toContain('description');
    expect(out.invalidNumbers).toBe(0);
    expect(out.skippedEmpty).toBe(0);
  });

  it('falls back to positional order when there is no header row', () => {
    const out = parseRows('Excavation\tm3\t50\t12.5');
    expect(out.rows).toHaveLength(1);
    expect(out.rows[0]).toMatchObject({
      description: 'Excavation',
      unit: 'm3',
      quantity: 50,
      unit_rate: 12.5,
    });
  });

  it('reads a European 1.234,56 grouping', () => {
    const out = parseRows('Rebar\tkg\t1.234,56\t1,45');
    expect(out.rows[0]?.quantity).toBeCloseTo(1234.56);
    expect(out.rows[0]?.unit_rate).toBeCloseTo(1.45);
    expect(out.invalidNumbers).toBe(0);
  });

  it('reads a US 1,234.56 grouping', () => {
    const out = parseRows('Formwork\tm2\t1,234.56\t22.00');
    expect(out.rows[0]?.quantity).toBeCloseTo(1234.56);
    expect(out.invalidNumbers).toBe(0);
  });

  it('counts an unreadable number and keeps a safe default instead of silent zero', () => {
    const out = parseRows('Description\tQty\nWall\tN/A');
    expect(out.rows).toHaveLength(1);
    // The bad quantity is not read as 0; it keeps the visible default (1) and
    // the modal warns the user via the invalidNumbers count.
    expect(out.rows[0]?.quantity).toBe(1);
    expect(out.invalidNumbers).toBe(1);
  });

  it('counts a line that has data but no description as skipped', () => {
    const out = parseRows('Description\tQty\n\t50');
    expect(out.rows).toHaveLength(0);
    expect(out.skippedEmpty).toBe(1);
  });

  it('does not flag empty numeric cells - they take the documented default', () => {
    // Quantity blank -> 1, rate blank -> 0, and neither counts as invalid.
    const out = parseRows('Description\tUnit\tQty\tRate\nDoor\tpcs\t\t');
    expect(out.rows[0]).toMatchObject({ quantity: 1, unit_rate: 0 });
    expect(out.invalidNumbers).toBe(0);
  });

  it('reports several problems across a mixed paste', () => {
    const raw = [
      'Description\tUnit\tQty\tRate',
      'Concrete\tm3\t10\t100', // clean
      'Steel\tkg\tzzz\t5', // bad quantity
      '\tm2\t4\t9', // no description
    ].join('\n');
    const out = parseRows(raw);
    expect(out.rows).toHaveLength(2);
    expect(out.invalidNumbers).toBe(1);
    expect(out.skippedEmpty).toBe(1);
  });
});
