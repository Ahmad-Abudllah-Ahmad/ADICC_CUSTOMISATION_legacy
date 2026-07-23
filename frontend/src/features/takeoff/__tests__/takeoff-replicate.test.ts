// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Pure tests for replicating measurements onto other pages (issue #332 wave,
 * the "typical floor" copy shortcut).
 */
import { describe, it, expect } from 'vitest';
import { replicateMeasurementsToPages } from '@/features/takeoff/lib/takeoff-replicate';
import type { Measurement } from '@/features/takeoff/lib/takeoff-types';

function mk(partial: Partial<Measurement>): Measurement {
  return {
    id: 'src1',
    type: 'area',
    points: [
      { x: 1, y: 2 },
      { x: 3, y: 4 },
      { x: 5, y: 6 },
    ],
    value: 10,
    unit: 'm²',
    label: '',
    annotation: 'Slab',
    page: 1,
    group: 'Concrete',
    serverId: 'srv-1',
    linkedPositionId: 'pos-1',
    linkedPositionOrdinal: 'TK.001',
    suggested: true,
    confidence: 0.7,
    ...partial,
  };
}

const idGen = (_s: Measurement, page: number, i: number): string => `clone_${page}_${i}`;

describe('replicateMeasurementsToPages', () => {
  it('clones a source onto each target page with the target page set', () => {
    const out = replicateMeasurementsToPages([mk({})], [2, 3], idGen);
    expect(out).toHaveLength(2);
    expect(out.map((m) => m.page).sort()).toEqual([2, 3]);
  });

  it('mints a fresh id per clone and clears server / link / suggestion identity', () => {
    const [clone] = replicateMeasurementsToPages([mk({})], [2], idGen);
    expect(clone!.id).toBe('clone_2_0');
    expect(clone!.serverId).toBeUndefined();
    expect(clone!.linkedPositionId).toBeUndefined();
    expect(clone!.linkedPositionOrdinal).toBeUndefined();
    expect(clone!.suggested).toBeUndefined();
    expect(clone!.confidence).toBeUndefined();
  });

  it('carries geometry, quantity and appearance across (deep-copied points)', () => {
    const src = mk({ value: 42, slopeFactor: 1.5, multiplier: 2, color: '#123456' });
    const [clone] = replicateMeasurementsToPages([src], [2], idGen);
    expect(clone!.value).toBe(42);
    expect(clone!.slopeFactor).toBe(1.5);
    expect(clone!.multiplier).toBe(2);
    expect(clone!.color).toBe('#123456');
    expect(clone!.points).toEqual(src.points);
    expect(clone!.points).not.toBe(src.points); // fresh array
    expect(clone!.points[0]).not.toBe(src.points[0]); // fresh point objects
  });

  it('never clones a measurement onto its own page', () => {
    // Source is on page 2; asking for pages [1,2,3] skips page 2.
    const out = replicateMeasurementsToPages([mk({ page: 2 })], [1, 2, 3], idGen);
    expect(out.map((m) => m.page).sort()).toEqual([1, 3]);
  });

  it('de-duplicates and sorts target pages', () => {
    const out = replicateMeasurementsToPages([mk({})], [3, 3, 2, 2], idGen);
    expect(out.map((m) => m.page)).toEqual([2, 3]);
  });

  it('skips invalid page numbers (< 1 or non-finite)', () => {
    const out = replicateMeasurementsToPages([mk({})], [0, -1, Number.NaN, 4], idGen);
    expect(out.map((m) => m.page)).toEqual([4]);
  });

  it('replicates a whole group (several sources) onto each page', () => {
    const sources = [mk({ id: 'a', page: 1 }), mk({ id: 'b', page: 1 })];
    const out = replicateMeasurementsToPages(sources, [2, 3], idGen);
    expect(out).toHaveLength(4); // 2 sources x 2 pages
    // Running index is unique across all clones so ids never collide.
    expect(new Set(out.map((m) => m.id)).size).toBe(4);
  });

  it('returns nothing for empty sources or empty pages', () => {
    expect(replicateMeasurementsToPages([], [2, 3], idGen)).toEqual([]);
    expect(replicateMeasurementsToPages([mk({})], [], idGen)).toEqual([]);
  });
});
