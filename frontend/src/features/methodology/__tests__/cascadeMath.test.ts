// @ts-nocheck
// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Unit tests for the client-side cascade preview engine. These pin the math to
// the backend engine (backend/app/modules/methodology/cascade.py) so the
// editor's live preview never drifts from the authoritative server compute.
// @ts-nocheck so step-result index access (r.steps[0]) is not flagged under
// noUncheckedIndexedAccess; the results are guaranteed present by construction.

import { describe, it, expect } from 'vitest';
import {
  computeCascadePreview,
  resolveBasesFromResourceTotals,
  roundTo,
  CascadePreviewError,
} from '../cascadeMath';
import type { MarkupStep } from '../types';

const step = (s: Partial<MarkupStep> & Pick<MarkupStep, 'key'>): MarkupStep => ({
  label: s.key,
  category: 'other',
  kind: 'percentage',
  rate: '0',
  amount: '0',
  base: [],
  ...s,
});

describe('roundTo', () => {
  it('rounds half up to the given places', () => {
    expect(roundTo(2.345, 2)).toBe(2.35);
    expect(roundTo(2.344, 2)).toBe(2.34);
    expect(roundTo(0.5, 0)).toBe(1);
    expect(roundTo(1.005, 2)).toBe(1.01);
  });

  it('treats non-finite input as 0', () => {
    expect(roundTo(NaN, 2)).toBe(0);
    expect(roundTo(Infinity, 2)).toBe(0);
  });
});

describe('resolveBasesFromResourceTotals', () => {
  it('sums resource totals per base token via the mapping', () => {
    const bases = resolveBasesFromResourceTotals(
      { labor: ['labor'], materials: ['material'], equipment: ['equipment'] },
      { labor: 100, material: 200, equipment: 50 },
    );
    expect(bases).toEqual({ labor: 100, materials: 200, equipment: 50 });
  });

  it('groups several resource types into one base (machinery into works)', () => {
    const bases = resolveBasesFromResourceTotals(
      { works: ['labor', 'machinery', 'material'], equipment: ['equipment'] },
      { labor: 100, machinery: 30, material: 200, equipment: 50 },
    );
    expect(bases).toEqual({ works: 330, equipment: 50 });
  });

  it('treats a mapped-but-absent resource type as 0', () => {
    const bases = resolveBasesFromResourceTotals(
      { labor: ['labor'], subcontract: ['subcontractor'] },
      { labor: 100 },
    );
    expect(bases).toEqual({ labor: 100, subcontract: 0 });
  });

  it('falls back to a single "direct" base when the mapping is empty', () => {
    const bases = resolveBasesFromResourceTotals({}, { labor: 100, material: 200 });
    expect(bases).toEqual({ direct: 300 });
  });
});

describe('computeCascadePreview - flat international (overhead 12, profit 8, vat 0)', () => {
  // Mirrors the international template: direct -> overhead 12% -> profit 8% on
  // (direct+overhead) -> vat 0%.
  const composites = { direct: ['labor', 'materials', 'equipment', 'subcontract'] };
  const steps: MarkupStep[] = [
    step({ key: 'overhead', category: 'overhead', rate: '12', base: ['direct'] }),
    step({ key: 'profit', category: 'profit', rate: '8', base: ['direct', 'overhead'] }),
    step({ key: 'vat', category: 'tax', rate: '0', base: ['direct', 'overhead', 'profit'] }),
  ];

  it('computes direct, markup and grand totals correctly', () => {
    const bases = { labor: 1000, materials: 0, equipment: 0, subcontract: 0 };
    const r = computeCascadePreview({ bases, composites, steps, decimals: 2 });

    expect(r.directTotal).toBe(1000);
    // overhead = 12% of 1000 = 120
    expect(r.steps[0].amount).toBe(120);
    // profit = 8% of (1000 + 120) = 89.6
    expect(r.steps[1].amount).toBe(89.6);
    // vat = 0
    expect(r.steps[2].amount).toBe(0);
    expect(r.markupTotal).toBe(209.6);
    expect(r.grandTotal).toBe(1209.6);
    // running totals feed forward
    expect(r.steps[0].runningTotal).toBe(1120);
    expect(r.steps[1].runningTotal).toBe(1209.6);
    expect(r.steps[2].runningTotal).toBe(1209.6);
  });

  it('resolves the direct composite as the sum of its members', () => {
    const bases = { labor: 600, materials: 300, equipment: 100, subcontract: 0 };
    const r = computeCascadePreview({ bases, composites, steps, decimals: 2 });
    expect(r.composites.direct).toBe(1000);
    expect(r.directTotal).toBe(1000);
  });
});

describe('computeCascadePreview - Germany (overhead 13, profit 6, vat 19)', () => {
  const composites = { direct: ['labor', 'materials', 'equipment', 'subcontract'] };
  const steps: MarkupStep[] = [
    step({ key: 'overhead', category: 'overhead', rate: '13', base: ['direct'] }),
    step({ key: 'profit', category: 'profit', rate: '6', base: ['direct', 'overhead'] }),
    step({ key: 'vat', category: 'tax', rate: '19', base: ['direct', 'overhead', 'profit'] }),
  ];

  it('applies VAT on top of direct + overhead + profit', () => {
    const bases = { labor: 0, materials: 1000, equipment: 0, subcontract: 0 };
    const r = computeCascadePreview({ bases, composites, steps, decimals: 2 });
    // overhead = 130, profit = 6% of 1130 = 67.80, base for vat = 1197.80
    expect(r.steps[0].amount).toBe(130);
    expect(r.steps[1].amount).toBe(67.8);
    // vat = 19% of 1197.80 = 227.582 -> 227.58
    expect(r.steps[2].amount).toBe(227.58);
    expect(r.grandTotal).toBe(1425.38);
  });
});

describe('computeCascadePreview - Uzbekistan cascade (SMR vs equipment)', () => {
  // SMR = labor + machinery + materials; installed equipment is a separate base
  // that skips the SMR-only steps but still carries insurance, contingency and
  // VAT. Mirrors the backend _UZBEKISTAN_TEMPLATE shape.
  const composites = { SMR: ['labor', 'machinery', 'materials'] };
  const steps: MarkupStep[] = [
    step({ key: 'other_temp_winter', category: 'temp_winter', rate: '0', base: ['SMR'] }),
    step({
      key: 'contractor_other',
      category: 'contractor_other',
      rate: '0',
      base: ['SMR', 'other_temp_winter'],
    }),
    step({
      key: 'insurance',
      category: 'insurance',
      rate: '0.32',
      base: ['SMR', 'equipment', 'other_temp_winter', 'contractor_other'],
    }),
    step({
      key: 'contingency',
      category: 'contingency',
      rate: '0',
      base: ['SMR', 'equipment', 'other_temp_winter', 'contractor_other', 'insurance'],
    }),
    step({
      key: 'vat',
      category: 'tax',
      rate: '12',
      base: ['SMR', 'equipment', 'other_temp_winter', 'contractor_other', 'insurance', 'contingency'],
    }),
  ];

  it('keeps installed equipment out of the SMR-only steps but in insurance and VAT', () => {
    // works (SMR) = 10000 + 5000 + 20000 = 35000; equipment = 8000.
    const bases = { labor: 10000, machinery: 5000, materials: 20000, equipment: 8000 };
    const r = computeCascadePreview({ bases, composites, steps, decimals: 2 });

    expect(r.composites.SMR).toBe(35000);
    expect(r.directTotal).toBe(43000);

    // temp_winter (0%) and contractor_other (0%) contribute nothing.
    expect(r.steps[0].amount).toBe(0);
    expect(r.steps[1].amount).toBe(0);

    // insurance base = SMR(35000) + equipment(8000) + 0 + 0 = 43000.
    // insurance = 0.32% of 43000 = 137.60
    expect(r.steps[2].baseAmount).toBe(43000);
    expect(r.steps[2].amount).toBe(137.6);

    // vat base = 35000 + 8000 + 0 + 0 + 137.60 = 43137.60.
    // vat = 12% of 43137.60 = 5176.512 -> 5176.51
    expect(r.steps[4].baseAmount).toBe(43137.6);
    expect(r.steps[4].amount).toBe(5176.51);

    expect(r.grandTotal).toBe(43000 + 137.6 + 5176.51);
  });
});

describe('computeCascadePreview - fixed-amount step', () => {
  it('applies a fixed amount regardless of base', () => {
    const steps: MarkupStep[] = [
      step({ key: 'mobilisation', kind: 'fixed', amount: '2500', base: [] }),
    ];
    const r = computeCascadePreview({
      bases: { labor: 1000 },
      composites: {},
      steps,
      decimals: 2,
    });
    expect(r.steps[0].amount).toBe(2500);
    expect(r.steps[0].rate).toBe(0);
    expect(r.grandTotal).toBe(3500);
  });
});

describe('computeCascadePreview - validation', () => {
  it('rejects a forward reference to a later step', () => {
    const steps: MarkupStep[] = [
      step({ key: 'a', rate: '10', base: ['direct', 'b'] }),
      step({ key: 'b', rate: '5', base: ['direct'] }),
    ];
    expect(() =>
      computeCascadePreview({ bases: { direct: 100 }, composites: {}, steps, decimals: 2 }),
    ).toThrow(CascadePreviewError);
  });

  it('rejects a self reference', () => {
    const steps: MarkupStep[] = [step({ key: 'a', rate: '10', base: ['a'] })];
    expect(() =>
      computeCascadePreview({ bases: { direct: 100 }, composites: {}, steps, decimals: 2 }),
    ).toThrow(/itself/);
  });

  it('rejects an unknown token', () => {
    const steps: MarkupStep[] = [step({ key: 'a', rate: '10', base: ['nope'] })];
    expect(() =>
      computeCascadePreview({ bases: { direct: 100 }, composites: {}, steps, decimals: 2 }),
    ).toThrow(/unknown token/);
  });

  it('rejects a duplicate step key', () => {
    const steps: MarkupStep[] = [
      step({ key: 'a', rate: '10', base: ['direct'] }),
      step({ key: 'a', rate: '5', base: ['direct'] }),
    ];
    expect(() =>
      computeCascadePreview({ bases: { direct: 100 }, composites: {}, steps, decimals: 2 }),
    ).toThrow(/duplicate/);
  });

  it('rejects a composite that references an unknown leaf base', () => {
    expect(() =>
      computeCascadePreview({
        bases: { labor: 100 },
        composites: { SMR: ['labor', 'machinery'] },
        steps: [],
        decimals: 2,
      }),
    ).toThrow(/unknown leaf base/);
  });

  it('allows a later step to reference an earlier one (no error)', () => {
    const steps: MarkupStep[] = [
      step({ key: 'overhead', rate: '10', base: ['direct'] }),
      step({ key: 'profit', rate: '5', base: ['direct', 'overhead'] }),
    ];
    expect(() =>
      computeCascadePreview({ bases: { direct: 1000 }, composites: {}, steps, decimals: 2 }),
    ).not.toThrow();
  });
});
