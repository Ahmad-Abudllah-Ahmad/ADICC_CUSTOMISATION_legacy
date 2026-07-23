// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
// Unit tests for the pure 6D auto-enrich helpers. No DOM / i18next needed.
import { describe, it, expect } from 'vitest';

import type { AutoEnrichBimResult, EmbodiedEntry } from './api';
import {
  summarizeEnrich,
  sourceLabel,
  sourcePillVariant,
  toNumber,
  formatCarbonKg,
  coverageTone,
  isDraftStatus,
  summarizeCompute,
  COVERAGE_GOOD_MIN,
} from './sixd';

function mkEntry(over: Partial<EmbodiedEntry> = {}): EmbodiedEntry {
  return {
    id: 'e1',
    inventory_id: 'inv1',
    element_id: 'el-1',
    source: 'auto_enriched',
    match_confidence: 'high',
    description: 'Wall',
    quantity: '9',
    unit: 'm3',
    factor_value_used: '300',
    carbon_kg: '2700',
    stage: 'a1a3',
    metadata: {},
    created_at: '',
    updated_at: '',
    ...over,
  };
}

function result(over: Partial<AutoEnrichBimResult> = {}): AutoEnrichBimResult {
  return {
    created: 0,
    skipped_no_match: 0,
    skipped_no_quantity: 0,
    entries: [],
    ...over,
  };
}

describe('summarizeEnrich', () => {
  it('counts matched proposals from entries, not the persisted counter (dry-run preview)', () => {
    // The backend reports created=0 during a dry-run preview (nothing persisted
    // yet) while still returning every proposal in `entries`. The summary must
    // reflect the proposals so the preview -> confirm flow stays reachable.
    const s = summarizeEnrich(
      result({
        created: 0,
        entries: [mkEntry(), mkEntry(), mkEntry()],
        skipped_no_match: 3,
        skipped_no_quantity: 5,
      }),
    );
    expect(s.created).toBe(3);
    expect(s.hasProposals).toBe(true);
    expect(s.totalSkipped).toBe(8);
    expect(s.totalConsidered).toBe(11);
  });

  it('reports no proposals when entries is empty', () => {
    const s = summarizeEnrich(result({ created: 0, skipped_no_match: 4, skipped_no_quantity: 2 }));
    expect(s.hasProposals).toBe(false);
    expect(s.totalSkipped).toBe(6);
    expect(s.totalConsidered).toBe(6);
  });

  it('folds skipped_existing into the totals (idempotency)', () => {
    const s = summarizeEnrich(
      result({ entries: [mkEntry()], skipped_no_match: 1, skipped_no_quantity: 2, skipped_existing: 4 }),
    );
    expect(s.created).toBe(1);
    expect(s.skippedExisting).toBe(4);
    expect(s.totalSkipped).toBe(7);
    expect(s.totalConsidered).toBe(8);
  });

  it('treats null / missing / negative counters as zero (never NaN)', () => {
    expect(summarizeEnrich(null)).toEqual({
      created: 0,
      skippedNoMatch: 0,
      skippedNoQuantity: 0,
      skippedExisting: 0,
      totalSkipped: 0,
      totalConsidered: 0,
      hasProposals: false,
    });
    const partial = { entries: [] } as unknown as AutoEnrichBimResult;
    expect(summarizeEnrich(partial).totalConsidered).toBe(0);
    const negative = result({ entries: [mkEntry()], skipped_no_match: -1, skipped_existing: -2 });
    const s = summarizeEnrich(negative);
    expect(s.skippedNoMatch).toBe(0);
    expect(s.skippedExisting).toBe(0);
    expect(Number.isNaN(s.totalConsidered)).toBe(false);
  });

  it('floors fractional counters (created fallback + skips)', () => {
    // When `entries` is absent the matched count falls back to the persisted
    // counter, which is floored like every other counter.
    const noEntries = { created: 2.9, skipped_no_quantity: 1.2 } as unknown as AutoEnrichBimResult;
    const s = summarizeEnrich(noEntries);
    expect(s.created).toBe(2);
    expect(s.skippedNoQuantity).toBe(1);
  });

  it('accepts a real EmbodiedEntry payload in entries', () => {
    const s = summarizeEnrich(result({ entries: [mkEntry({ unit: 'm3' })] }));
    expect(s.created).toBe(1);
    expect(s.hasProposals).toBe(true);
  });
});

describe('sourceLabel', () => {
  it('maps each known source to its key + default', () => {
    expect(sourceLabel('auto_enriched')).toEqual({
      key: 'carbon.sixd.source_auto',
      defaultValue: 'Auto from BIM',
    });
    expect(sourceLabel('boq_derived')).toEqual({
      key: 'carbon.sixd.source_boq',
      defaultValue: 'From BOQ',
    });
    expect(sourceLabel('manual')).toEqual({
      key: 'carbon.sixd.source_manual',
      defaultValue: 'Manual',
    });
  });

  it('falls back to manual for null / undefined (legacy rows)', () => {
    expect(sourceLabel(null).key).toBe('carbon.sixd.source_manual');
    expect(sourceLabel(undefined).key).toBe('carbon.sixd.source_manual');
  });
});

describe('sourcePillVariant', () => {
  it('highlights auto-from-BIM and keeps the rest neutral', () => {
    expect(sourcePillVariant('auto_enriched')).toBe('blue');
    expect(sourcePillVariant('boq_derived')).toBe('neutral');
    expect(sourcePillVariant('manual')).toBe('neutral');
    expect(sourcePillVariant(null)).toBe('neutral');
  });
});

describe('toNumber', () => {
  it('coerces strings and numbers, never returns NaN', () => {
    expect(toNumber('228000')).toBe(228000);
    expect(toNumber(9)).toBe(9);
    expect(toNumber('12.5')).toBe(12.5);
    expect(toNumber(null)).toBe(0);
    expect(toNumber(undefined)).toBe(0);
    expect(toNumber('not-a-number')).toBe(0);
    expect(toNumber(Number.POSITIVE_INFINITY)).toBe(0);
  });
});

describe('formatCarbonKg', () => {
  it('scales to kg / t / kt', () => {
    expect(formatCarbonKg(500)).toBe('500 kg');
    expect(formatCarbonKg(2700)).toBe('2.70 t');
    expect(formatCarbonKg(228000)).toBe('228.00 t');
    expect(formatCarbonKg(1_500_000)).toBe('1.50 kt');
  });

  it('keeps the sign for module-D credits', () => {
    expect(formatCarbonKg(-2000)).toBe('-2.00 t');
  });
});

describe('coverageTone', () => {
  it('maps a percentage to a traffic-light band', () => {
    expect(coverageTone(0)).toBe('none');
    expect(coverageTone(1)).toBe('partial');
    expect(coverageTone(COVERAGE_GOOD_MIN - 0.1)).toBe('partial');
    expect(coverageTone(COVERAGE_GOOD_MIN)).toBe('good');
    expect(coverageTone(100)).toBe('good');
  });

  it('treats missing / invalid input as no coverage', () => {
    expect(coverageTone(null)).toBe('none');
    expect(coverageTone(undefined)).toBe('none');
    expect(coverageTone(Number.NaN)).toBe('none');
    expect(coverageTone(-5)).toBe('none');
  });
});

describe('isDraftStatus', () => {
  it('is true only for a draft line', () => {
    expect(isDraftStatus('draft')).toBe(true);
    expect(isDraftStatus('confirmed')).toBe(false);
    expect(isDraftStatus(null)).toBe(false);
    expect(isDraftStatus(undefined)).toBe(false);
  });
});

describe('summarizeCompute', () => {
  it('counts proposals from entries during a dry run (created=0)', () => {
    const s = summarizeCompute({
      created: 0,
      skipped_no_energy: 2,
      skipped_existing: 1,
      entries: [{}, {}, {}],
    });
    expect(s.created).toBe(3);
    expect(s.skipped).toBe(3);
    expect(s.total).toBe(6);
    expect(s.hasProposals).toBe(true);
  });

  it('folds the whole-life-cost skip counter (skipped_no_cost)', () => {
    const s = summarizeCompute({
      entries: [{}],
      skipped_no_cost: 4,
      skipped_existing: 1,
    });
    expect(s.created).toBe(1);
    expect(s.skipped).toBe(5);
    expect(s.total).toBe(6);
  });

  it('falls back to the persisted counter when entries is absent', () => {
    const s = summarizeCompute({ created: 2, skipped_no_energy: 1 });
    expect(s.created).toBe(2);
    expect(s.skipped).toBe(1);
    expect(s.hasProposals).toBe(true);
  });

  it('never returns NaN for a null / malformed payload', () => {
    expect(summarizeCompute(null)).toEqual({
      created: 0,
      skipped: 0,
      total: 0,
      hasProposals: false,
    });
    const partial = { entries: [] } as ComputeCountersLike;
    expect(summarizeCompute(partial).hasProposals).toBe(false);
  });
});

// Local structural alias so the malformed-payload test above can pass an empty
// object without importing the exported interface name into every assertion.
type ComputeCountersLike = { entries?: unknown[] | null };
