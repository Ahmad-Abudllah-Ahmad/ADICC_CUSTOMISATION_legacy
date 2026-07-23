// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Tests for the BIM filter-report helpers (B5): the quantity summariser and
 * the printable-HTML builder. These mirror the backend BOQ exporter's
 * grouping + alias scan, so the on-screen / printed numbers match the Excel.
 */
import { describe, it, expect } from 'vitest';
import type { BIMElementData } from '@/shared/ui/BIMViewer';
import { summariseBimQuantities, round3 } from '../boqSummary';
import { escapeHtml, buildReportHtml } from '../printReport';

const els = [
  { id: 'wa', element_type: 'IfcWall', storey: 'L1', quantities: { area_m2: 10, volume_m3: 2 } },
  { id: 'wb', element_type: 'IfcWall', storey: 'L2', quantities: { area: 5, NetVolume: 1 } }, // aliases
  { id: 'wbad', element_type: 'IfcWall', storey: 'L1', quantities: { area_m2: true } }, // bool rejected
  { id: 'sl', element_type: 'IfcSlab', storey: 'L1', quantities: { area_m2: 50, volume_m3: 12.5, weight_kg: '300' } },
  { id: 'bm', element_type: 'IfcBeam', storey: 'L1', quantities: { length_m: 8 } },
] as unknown as BIMElementData[];

describe('round3', () => {
  it('rounds float dust', () => {
    expect(round3(0.1 + 0.2)).toBe(0.3);
  });
});

describe('summariseBimQuantities by element_type', () => {
  const s = summariseBimQuantities(els, 'element_type');

  it('sorts groups and counts them', () => {
    expect(s.rows.map((r) => r.key)).toEqual(['IfcBeam', 'IfcSlab', 'IfcWall']);
    expect(s.rows.find((r) => r.key === 'IfcWall')!.count).toBe(3);
  });

  it('sums quantities, scanning aliases and rejecting a bool', () => {
    const wall = s.rows.find((r) => r.key === 'IfcWall')!;
    // [area, volume, length, weight]; alias area on wb=5, bool on wbad=0 -> 15 area, 3 volume
    expect(wall.quantities).toEqual([15, 3, 0, 0]);
    const slab = s.rows.find((r) => r.key === 'IfcSlab')!;
    expect(slab.quantities).toEqual([50, 12.5, 0, 300]); // string '300' coerced
  });

  it('totals across all groups', () => {
    expect(s.totals.count).toBe(5);
    expect(s.totals.quantities).toEqual([65, 15.5, 8, 300]);
  });
});

describe('summariseBimQuantities by storey', () => {
  const s = summariseBimQuantities(els, 'storey');
  it('groups and sums per storey', () => {
    expect(s.rows.map((r) => r.key)).toEqual(['L1', 'L2']);
    const l1 = s.rows.find((r) => r.key === 'L1')!;
    expect(l1.count).toBe(4);
    expect(l1.quantities).toEqual([60, 14.5, 8, 300]);
  });
});

describe('printReport helpers', () => {
  it('escapes HTML special characters', () => {
    expect(escapeHtml('<b>&"\'')).toBe('&lt;b&gt;&amp;&quot;&#39;');
  });

  it('builds a report document with the title, scope, and a total', () => {
    const summary = summariseBimQuantities(els, 'element_type');
    const html = buildReportHtml({
      title: 'Quantity report - Tower A',
      scopeLabel: 'Whole model',
      generatedOn: '2026-06-29 10:00',
      sections: [{ heading: 'By element type', groupLabel: 'Element type', summary }],
    });
    expect(html).toContain('Quantity report - Tower A');
    expect(html).toContain('Whole model');
    expect(html).toContain('By element type');
    expect(html).toContain('65'); // total area appears in the TOTAL row
    expect(html.startsWith('<!DOCTYPE html>')).toBe(true);
  });

  it('defaults to metric: canonical values + metric unit headers (#285)', () => {
    const summary = summariseBimQuantities(els, 'element_type');
    const html = buildReportHtml({
      title: 'Q',
      scopeLabel: 'Whole model',
      generatedOn: 'now',
      sections: [{ heading: 'By element type', groupLabel: 'Element type', summary }],
    });
    // Metric labels are normalised to their display form (m2 -> m²).
    expect(html).toContain(`Area (m${'²'})`);
    expect(html).toContain(`Volume (m${'³'})`);
    expect(html).toContain('65'); // area total passes through unconverted
    expect(html).not.toContain('sq ft');
  });

  it('restates quantity columns + headers for imperial (#285)', () => {
    const summary = summariseBimQuantities(els, 'element_type');
    const html = buildReportHtml({
      title: 'Q',
      scopeLabel: 'Whole model',
      generatedOn: 'now',
      system: 'imperial',
      sections: [{ heading: 'By element type', groupLabel: 'Element type', summary }],
    });
    // Headers relabel to the imperial units.
    expect(html).toContain('Area (sq ft)');
    expect(html).toContain('Volume (cu ft)');
    expect(html).toContain('Weight (lb)');
    // 65 m2 -> 65 * 10.7639 = 699.6535 -> "699.654" in the TOTAL row.
    expect(html).toContain('699.654');
    // 8 m length -> 8 * 3.2808399 = 26.2467... -> "26.247".
    expect(html).toContain('26.247');
    // The canonical metric area total must NOT leak into the imperial doc as
    // a standalone cell, and the metric header must be gone.
    expect(html).not.toContain(`Area (m${'²'})`);
    // Count is not a quantity column - it is invariant across systems.
    expect(html).toContain('<td class="num">5</td>');
  });
});
