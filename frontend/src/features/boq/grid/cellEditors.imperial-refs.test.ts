// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Regression guard for the imperial BOQ money path (Issue #292 + H2 fix).
 *
 * A quantity-cell formula can reference symbols that are all stored
 * metric-canonical: another position (=pos("01.005").qty / .rate / .total), a
 * section aggregate, or a BOQ variable (=$GFA). BOQ variables carry no unit, so
 * the editor evaluates a formula in METRIC space - positions are NOT projected
 * into the display unit - and, when the formula references one of these
 * canonical symbols, stores the resolved value as-is: it must NOT be run through
 * the display->metric seam again. A pure-literal formula (=10+6) or a plain
 * typed number carries no reference, so it is read in the displayed unit and
 * converted display->metric exactly once.
 *
 * The earlier model projected positions into the display unit but passed
 * variables through raw and then always divided by the cell's unit factor, so a
 * dimensional =$GFA in imperial mode silently stored ~10.76x the metric quantity
 * the same formula stored in metric mode. These tests lock the stored value in
 * both measurement systems against the real conversion primitives, with an
 * explicit no-divergence assertion for the variable path.
 */
import { describe, it, expect } from 'vitest';

import { buildFormulaContext, evaluateFormula, extractReferences } from './formula';
import type { FormulaVariable } from './formula';
import type { Position } from '../api';
import { fromDisplayQuantity } from '@/shared/lib/unitConversion';

type System = 'metric' | 'imperial';

// A position carrying just the fields the formula engine reads (ordinal, id,
// quantity, unit_rate); the rest of Position is irrelevant here.
function makePosition(ordinal: string, quantityMetric: number, unit: string): Position {
  return {
    id: ordinal,
    ordinal,
    unit,
    quantity: quantityMetric,
    unit_rate: 0,
  } as unknown as Position;
}

// Mirror what FormulaCellEditor now does: evaluate against raw (metric)
// positions, never projected into the display unit.
function metricContext(positions: Position[], variables?: Map<string, FormulaVariable>) {
  return buildFormulaContext({ positions, variables });
}

// Mirror the editor's commit seam (parseInput -> commitFromInput): a formula
// that references a canonical symbol is stored as-is; anything else is a
// displayed value converted display->metric exactly once.
function storeFromEditor(src: string, resolved: number, unit: string, system: System): number {
  const refs = extractReferences(src);
  const canonical =
    refs.variables.size > 0 || refs.positionOrdinals.size > 0 || refs.sectionNames.size > 0;
  return canonical ? resolved : fromDisplayQuantity(resolved, unit, system);
}

function boqVars(entries: Record<string, number>): Map<string, FormulaVariable> {
  const m = new Map<string, FormulaVariable>();
  for (const [k, v] of Object.entries(entries)) {
    m.set(k.toUpperCase(), { type: 'number', value: v });
  }
  return m;
}

describe('imperial BOQ quantity formulas store metric-canonical, identical in both systems (#292 / H2)', () => {
  it('=pos().qty stores the referenced metric quantity, same in metric and imperial', () => {
    const positions = [makePosition('01.001', 3.048, 'm')];
    const src = '=pos("01.001").qty';
    for (const system of ['metric', 'imperial'] as System[]) {
      const resolved = evaluateFormula(src, metricContext(positions));
      expect(resolved).not.toBeNull();
      expect(storeFromEditor(src, resolved as number, 'm', system)).toBeCloseTo(3.048, 6);
    }
  });

  it('=pos().qty area reference stores the referenced m2, same in both systems', () => {
    const positions = [makePosition('02.001', 10, 'm2')];
    const src = '=pos("02.001").qty';
    for (const system of ['metric', 'imperial'] as System[]) {
      const resolved = evaluateFormula(src, metricContext(positions));
      expect(storeFromEditor(src, resolved as number, 'm2', system)).toBeCloseTo(10, 6);
    }
  });

  it('=pos().qty * 2 stores 2x the metric quantity, same in both systems', () => {
    const positions = [makePosition('01.001', 3.048, 'm')];
    const src = '=pos("01.001").qty * 2';
    for (const system of ['metric', 'imperial'] as System[]) {
      const resolved = evaluateFormula(src, metricContext(positions));
      expect(storeFromEditor(src, resolved as number, 'm', system)).toBeCloseTo(6.096, 6);
    }
  });

  it('H2: a dimensional variable =$GFA * 0.15 stores the SAME metric value in metric and imperial', () => {
    const vars = boqVars({ GFA: 1500 }); // e.g. 1500 m2 stored canonical
    const src = '=$GFA * 0.15';
    const stores = (['metric', 'imperial'] as System[]).map((system) => {
      const r = evaluateFormula(src, metricContext([], vars));
      expect(r).not.toBeNull();
      return storeFromEditor(src, r as number, 'm2', system);
    });
    expect(stores[0]).toBeCloseTo(225, 6); // metric
    // The bug this guards: the imperial store must not diverge (was ~20.9 m2).
    expect(stores[1]).toBeCloseTo(225, 6); // imperial
    expect(stores[1]).toBeCloseTo(stores[0] as number, 9);
  });

  it('H2: a mixed formula =pos().qty + $GFA stays canonical and identical across systems', () => {
    const positions = [makePosition('01.001', 10, 'm2')];
    const vars = boqVars({ GFA: 5 });
    const src = '=pos("01.001").qty + $GFA';
    const stores = (['metric', 'imperial'] as System[]).map((system) => {
      const r = evaluateFormula(src, metricContext(positions, vars));
      return storeFromEditor(src, r as number, 'm2', system);
    });
    expect(stores[0]).toBeCloseTo(15, 6);
    expect(stores[1]).toBeCloseTo(15, 6); // no divergence
  });

  it('a pure-literal formula (no reference) is still read in the displayed unit and converted once', () => {
    const src = '=10 + 6';
    // No references -> treated as a displayed value, not canonical.
    expect(extractReferences(src).variables.size).toBe(0);
    expect(extractReferences(src).positionOrdinals.size).toBe(0);
    const r = evaluateFormula(src, metricContext([]));
    expect(r as number).toBeCloseTo(16, 6);
    // metric: stored as typed; imperial foot cell: 16 ft -> metres, once.
    expect(storeFromEditor(src, r as number, 'm', 'metric')).toBeCloseTo(16, 6);
    expect(storeFromEditor(src, r as number, 'm', 'imperial')).toBeCloseTo(4.8768, 4);
  });
});
