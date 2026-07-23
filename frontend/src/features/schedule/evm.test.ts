// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';
import {
  classifyIndex,
  formatIndex,
  isVarianceFavourable,
  hasEvmCostData,
  tallySnapshot,
  snapshotTotal,
  clampDateIso,
  deriveScrubberRange,
  daysBetweenIso,
  addDaysIso,
  SNAPSHOT_STATUS_ORDER,
} from './evm';
import type { EvmSummary, ScheduleSnapshot } from './api';

describe('classifyIndex', () => {
  it('bands an index around the 1.0 baseline with an epsilon', () => {
    expect(classifyIndex(1.2)).toBe('ahead');
    expect(classifyIndex(1.0)).toBe('on_track');
    expect(classifyIndex(0.999)).toBe('on_track'); // within epsilon
    expect(classifyIndex(1.001)).toBe('on_track'); // within epsilon
    expect(classifyIndex(0.83)).toBe('behind');
  });

  it('returns unknown for null / non-finite indices', () => {
    expect(classifyIndex(null)).toBe('unknown');
    expect(classifyIndex(undefined)).toBe('unknown');
    expect(classifyIndex(Number.NaN)).toBe('unknown');
    expect(classifyIndex(Number.POSITIVE_INFINITY)).toBe('unknown');
  });
});

describe('formatIndex', () => {
  it('formats to two decimals', () => {
    expect(formatIndex(0.8333)).toBe('0.83');
    expect(formatIndex(1.0417)).toBe('1.04');
  });
  it('uses a plain-hyphen placeholder (no em-dash) for unknown', () => {
    expect(formatIndex(null)).toBe('-');
    expect(formatIndex(undefined, 'n/a')).toBe('n/a');
    // Guard against an em-dash slipping into the default placeholder.
    expect(formatIndex(null)).not.toContain('—');
  });
});

describe('isVarianceFavourable', () => {
  it('treats >= 0 as favourable (ahead / under budget)', () => {
    expect(isVarianceFavourable(100)).toBe(true);
    expect(isVarianceFavourable(0)).toBe(true);
    expect(isVarianceFavourable(-50)).toBe(false);
  });
});

describe('hasEvmCostData', () => {
  it('reads the has_cost_data flag defensively', () => {
    expect(hasEvmCostData(null)).toBe(false);
    expect(hasEvmCostData(undefined)).toBe(false);
    expect(hasEvmCostData({ has_cost_data: false } as EvmSummary)).toBe(false);
    expect(hasEvmCostData({ has_cost_data: true } as EvmSummary)).toBe(true);
  });
});

function makeSnapshot(elements: Record<string, string>): ScheduleSnapshot {
  return {
    schedule_id: 's1',
    as_of_date: '2026-01-15',
    model_version_id: null,
    elements,
  };
}

describe('tallySnapshot', () => {
  it('counts statuses in canonical worst-first order', () => {
    const snap = makeSnapshot({
      e1: 'completed',
      e2: 'delayed',
      e3: 'in_progress',
      e4: 'in_progress',
      e5: 'completed',
      e6: 'not_started',
    });
    const tally = tallySnapshot(snap);
    expect(tally).toEqual([
      { status: 'delayed', count: 1 },
      { status: 'in_progress', count: 2 },
      { status: 'not_started', count: 1 },
      { status: 'completed', count: 2 },
    ]);
    // Order matches the canonical worst-first sequence (minus absent buckets).
    const order = tally.map((t) => t.status);
    const canonicalFiltered = SNAPSHOT_STATUS_ORDER.filter((s) => order.includes(s));
    expect(order).toEqual(canonicalFiltered);
  });

  it('appends unknown statuses after the known ones, alphabetically', () => {
    const tally = tallySnapshot(makeSnapshot({ a: 'zeta', b: 'completed', c: 'alpha' }));
    expect(tally).toEqual([
      { status: 'completed', count: 1 },
      { status: 'alpha', count: 1 },
      { status: 'zeta', count: 1 },
    ]);
  });

  it('returns [] for an empty / missing snapshot', () => {
    expect(tallySnapshot(null)).toEqual([]);
    expect(tallySnapshot(makeSnapshot({}))).toEqual([]);
  });
});

describe('snapshotTotal', () => {
  it('counts linked elements', () => {
    expect(snapshotTotal(makeSnapshot({ a: 'completed', b: 'delayed' }))).toBe(2);
    expect(snapshotTotal(null)).toBe(0);
  });
});

describe('clampDateIso', () => {
  it('clamps into the [min, max] window', () => {
    expect(clampDateIso('2026-01-01', '2026-02-01', '2026-03-01')).toBe('2026-02-01');
    expect(clampDateIso('2026-04-01', '2026-02-01', '2026-03-01')).toBe('2026-03-01');
    expect(clampDateIso('2026-02-15', '2026-02-01', '2026-03-01')).toBe('2026-02-15');
  });
  it('passes through when bounds are missing', () => {
    expect(clampDateIso('2026-02-15')).toBe('2026-02-15');
    expect(clampDateIso('', '2026-01-01', '2026-03-01')).toBe('');
  });
});

describe('deriveScrubberRange', () => {
  const TODAY = '2026-06-20';
  it('uses both bounds when present', () => {
    expect(deriveScrubberRange('2026-01-01', '2026-12-31', TODAY)).toEqual({
      min: '2026-01-01',
      max: '2026-12-31',
    });
  });
  it('swaps an inverted range so min <= max', () => {
    expect(deriveScrubberRange('2026-12-31', '2026-01-01', TODAY)).toEqual({
      min: '2026-01-01',
      max: '2026-12-31',
    });
  });
  it('extends a start-only range to today when today is later', () => {
    expect(deriveScrubberRange('2026-01-01', null, TODAY)).toEqual({
      min: '2026-01-01',
      max: TODAY,
    });
    // Start in the future: max stays the start (no negative window).
    expect(deriveScrubberRange('2026-12-01', null, TODAY)).toEqual({
      min: '2026-12-01',
      max: '2026-12-01',
    });
  });
  it('falls back to a today-only window when both bounds are missing', () => {
    expect(deriveScrubberRange(null, undefined, TODAY)).toEqual({ min: TODAY, max: TODAY });
  });
});

describe('daysBetweenIso / addDaysIso', () => {
  it('counts whole days between ISO dates (UTC-safe)', () => {
    expect(daysBetweenIso('2026-01-01', '2026-01-11')).toBe(10);
    expect(daysBetweenIso('2026-01-11', '2026-01-01')).toBe(-10);
    expect(daysBetweenIso('2026-01-01', '2026-01-01')).toBe(0);
    // Spans a DST boundary in many zones - must still be exactly 31 days.
    expect(daysBetweenIso('2026-03-01', '2026-04-01')).toBe(31);
  });

  it('returns 0 for unparseable input', () => {
    expect(daysBetweenIso('not-a-date', '2026-01-01')).toBe(0);
  });

  it('adds days and round-trips with daysBetweenIso', () => {
    expect(addDaysIso('2026-01-01', 10)).toBe('2026-01-11');
    expect(addDaysIso('2026-01-11', -10)).toBe('2026-01-01');
    expect(addDaysIso('2026-01-01', 0)).toBe('2026-01-01');
    const base = '2026-06-20';
    for (const d of [0, 1, 5, 33, 200]) {
      expect(daysBetweenIso(base, addDaysIso(base, d))).toBe(d);
    }
  });

  it('passes through unparseable input unchanged', () => {
    expect(addDaysIso('garbage', 5)).toBe('garbage');
  });
});
