// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Issue #285 - imperial-aware editable BOQ grid.
 *
 * The grid stores every quantity metric-canonical and only converts the
 * human-facing output. The cardinal rule: whenever a quantity is DISPLAYED
 * converted, the paired per-unit rate is shown RECIPROCALLY so the line
 * reconciles, and the money total is INVARIANT (never recomputed from the
 * converted numbers).
 *
 * The Qty / Unit / Unit-rate renderers + the resource / variant inline
 * editors are React components wired to AG Grid params, i18n and the
 * preferences store, so they are exercised end-to-end by the browser /
 * BOQGrid suites. Here we lock down the exact conversion math each of those
 * call sites performs against the shared foundation helpers - the same
 * functions the grid threads through ``useDisplayQuantity``:
 *
 *   - Qty cell render    -> toDisplayQuantity(value, unit, system).value
 *   - Qty value parser   -> fromDisplayQuantity(typed, unit, system)
 *   - Unit cell render   -> displayUnitFor(unit, system)
 *   - Rate cell render    -> toDisplayRate(rate, unit, system)
 *   - Rate value parser   -> fromDisplayRate(typed, unit, system)
 *   - Total cell render   -> stored canonical total, UNCHANGED
 *
 * Proving these here means the grid's display path converts, the edit path
 * reverses cleanly back to metric storage, and displayed_qty * displayed_rate
 * reconciles to the stored total.
 */

import { describe, it, expect } from 'vitest';
import {
  toDisplayQuantity,
  displayUnitFor,
  fromDisplayQuantity,
  toDisplayRate,
  fromDisplayRate,
} from '@/shared/lib/unitConversion';

const FT_PER_M = 3.2808399;

describe('#285 grid quantity cell - display conversion', () => {
  it('metric: renders the stored value + unit unchanged', () => {
    expect(toDisplayQuantity(2.31, 'm', 'metric')).toEqual({ value: 2.31, unit: 'm' });
    expect(displayUnitFor('m', 'metric')).toBe('m');
  });

  it('imperial: renders the stored metric value converted (m -> ft)', () => {
    const shown = toDisplayQuantity(2.31, 'm', 'imperial');
    expect(shown.value).toBeCloseTo(2.31 * FT_PER_M, 6); // 7.58 ft
    expect(shown.unit).toBe('ft');
    expect(displayUnitFor('m', 'imperial')).toBe('ft');
  });

  it('imperial: area / weight relabel to imperial display units', () => {
    expect(displayUnitFor('m²', 'imperial')).toBe('ft²');
    expect(displayUnitFor('m2', 'imperial')).toBe('sq ft');
    expect(displayUnitFor('kg', 'imperial')).toBe('lb');
  });

  it('unmapped units (pcs / %) pass through in both systems', () => {
    expect(toDisplayQuantity(5, 'pcs', 'imperial')).toEqual({ value: 5, unit: 'pcs' });
    expect(displayUnitFor('%', 'imperial')).toBe('%');
  });
});

describe('#285 grid quantity value parser - edit reverses to metric storage', () => {
  it('metric: the typed value is stored as-is', () => {
    expect(fromDisplayQuantity(2.31, 'm', 'metric')).toBe(2.31);
  });

  it('imperial: a value typed in ft is stored as metres (round-trip)', () => {
    // User sees 7.58 ft, edits it; storage must land back on ~2.31 m.
    const displayed = toDisplayQuantity(2.31, 'm', 'imperial').value;
    const stored = fromDisplayQuantity(displayed, 'm', 'imperial');
    expect(stored).toBeCloseTo(2.31, 9);
  });

  it('imperial: editing a fresh ft value stores the metric equivalent', () => {
    // Type 10 ft -> store 3.048 m.
    expect(fromDisplayQuantity(10, 'm', 'imperial')).toBeCloseTo(3.048, 6);
  });

  it('the cardinal sin is never committed: storage is metric, not the typed imperial number', () => {
    const typedFt = 7.58;
    const stored = fromDisplayQuantity(typedFt, 'm', 'imperial');
    expect(stored).not.toBeCloseTo(typedFt, 2);
    expect(stored).toBeCloseTo(7.58 / FT_PER_M, 6);
  });
});

describe('#285 grid unit-rate cell - reciprocal display + reverse', () => {
  it('metric: the rate renders unchanged', () => {
    expect(toDisplayRate(50, 'm', 'metric')).toBe(50);
  });

  it('imperial: a per-metre rate renders per-foot reciprocally (50/m -> 15.24/ft)', () => {
    expect(toDisplayRate(50, 'm', 'imperial')).toBeCloseTo(50 / FT_PER_M, 6); // 15.24
  });

  it('imperial: a rate typed per-foot reverses to per-metre storage', () => {
    const displayed = toDisplayRate(50, 'm', 'imperial'); // 15.24 / ft
    const stored = fromDisplayRate(displayed, 'm', 'imperial');
    expect(stored).toBeCloseTo(50, 9);
  });

  it('unmapped units keep the rate unchanged both ways', () => {
    expect(toDisplayRate(12, 'pcs', 'imperial')).toBe(12);
    expect(fromDisplayRate(12, 'pcs', 'imperial')).toBe(12);
  });
});

describe('#285 line reconciliation - displayed_qty * displayed_rate == stored total', () => {
  // The example from the issue: 2.31 m at 50/m = 115.50 must read in imperial
  // as 7.58 ft at 15.24/ft = 115.50. The money total is invariant.
  const cases: Array<{ qty: number; rate: number; unit: string }> = [
    { qty: 2.31, rate: 50, unit: 'm' },
    { qty: 10, rate: 12.5, unit: 'm²' },
    { qty: 4.2, rate: 80, unit: 'm3' },
    { qty: 1250, rate: 1.1, unit: 'kg' },
    { qty: 3, rate: 200, unit: 'pcs' }, // unmapped: passes through unchanged
  ];

  it.each(cases)('reconciles $unit in metric (no-op) and imperial', ({ qty, rate, unit }) => {
    const storedTotal = qty * rate; // money total - canonical, never recomputed from converted numbers

    // Metric: identity, so the displayed pair equals storage exactly.
    const mQty = toDisplayQuantity(qty, unit, 'metric').value;
    const mRate = toDisplayRate(rate, unit, 'metric');
    expect(mQty * mRate).toBeCloseTo(storedTotal, 6);

    // Imperial: qty scales up, rate scales down reciprocally, product holds.
    const iQty = toDisplayQuantity(qty, unit, 'imperial').value;
    const iRate = toDisplayRate(rate, unit, 'imperial');
    expect(iQty * iRate).toBeCloseTo(storedTotal, 6);
  });

  it('an edit round-trip (display -> store -> display) preserves the total', () => {
    const qty = 2.31;
    const rate = 50;
    const unit = 'm';
    const storedTotal = qty * rate;

    // 1. Display in imperial.
    const iQty = toDisplayQuantity(qty, unit, 'imperial').value;
    const iRate = toDisplayRate(rate, unit, 'imperial');

    // 2. User re-commits the same displayed numbers; grid stores metric.
    const storedQty = fromDisplayQuantity(iQty, unit, 'imperial');
    const storedRate = fromDisplayRate(iRate, unit, 'imperial');

    // 3. Storage is back to canonical metric and the total is unchanged.
    expect(storedQty).toBeCloseTo(qty, 9);
    expect(storedRate).toBeCloseTo(rate, 9);
    expect(storedQty * storedRate).toBeCloseTo(storedTotal, 6);
  });
});

describe('#285 resource + variant rows - same convert / reverse contract', () => {
  // EditableResourceRow / VariantHeaderResourceRow convert qty via
  // convert/toMetric and rate via convertRate/toMetricRate against the
  // resource's own unit, leaving the metric total (qty*rate) invariant.
  it('resource qty + rate display converted and reverse to metric', () => {
    const resQty = 0.75; // m3 of concrete per unit
    const resRate = 120; // per m3
    const unit = 'm3';
    const total = resQty * resRate;

    const dispQty = toDisplayQuantity(resQty, unit, 'imperial').value;
    const dispRate = toDisplayRate(resRate, unit, 'imperial');
    expect(dispQty * dispRate).toBeCloseTo(total, 6);

    expect(fromDisplayQuantity(dispQty, unit, 'imperial')).toBeCloseTo(resQty, 9);
    expect(fromDisplayRate(dispRate, unit, 'imperial')).toBeCloseTo(resRate, 9);
  });
});
