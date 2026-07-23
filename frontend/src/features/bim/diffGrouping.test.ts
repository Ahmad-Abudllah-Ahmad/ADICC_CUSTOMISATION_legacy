// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';
import { groupModelDiff, formatDiffValue } from './diffGrouping';
import type { BIMModelDiff } from './api';

function makeDiff(): BIMModelDiff {
  return {
    id: 'd1',
    old_model_id: 'old',
    new_model_id: 'new',
    diff_summary: { unchanged: 10, modified: 2, added: 2, deleted: 1 },
    diff_details: {
      added: [
        { stable_id: 'a1', element_type: 'Walls', name: 'New Wall' },
        { stable_id: 'a2', element_type: 'Doors', name: 'New Door' },
      ],
      deleted: [{ stable_id: 'd1e', element_type: 'Walls', name: 'Old Wall' }],
      modified: [
        {
          stable_id: 'm1',
          element_type: 'Walls',
          changes: [
            { field: 'geometry_hash', old: 'aaa', new: 'bbb' },
            { field: 'quantities', old: { area: 10 }, new: { area: 12 } },
          ],
        },
        {
          stable_id: 'm2',
          element_type: 'Windows',
          changes: [{ field: 'element_type', old: 'Window', new: 'Glazing' }],
        },
      ],
    },
    metadata: {},
    created_at: '2026-05-18T00:00:00Z',
    updated_at: '2026-05-18T00:00:00Z',
  };
}

describe('diffGrouping.groupModelDiff', () => {
  it('groups by category with correct per-bucket counts', () => {
    const g = groupModelDiff(makeDiff());
    const walls = g.groups.find((x) => x.category === 'Walls');
    expect(walls).toBeDefined();
    // Walls: 1 added, 1 deleted, 1 modified.
    expect(walls!.added).toBe(1);
    expect(walls!.deleted).toBe(1);
    expect(walls!.modified).toBe(1);
    expect(walls!.total).toBe(3);
  });

  it('sorts the busiest category first', () => {
    const g = groupModelDiff(makeDiff());
    expect(g.groups[0]!.category).toBe('Walls'); // 3 changes — the most
  });

  it('orders rows deleted → modified → added inside a group', () => {
    const g = groupModelDiff(makeDiff());
    const walls = g.groups.find((x) => x.category === 'Walls')!;
    expect(walls.rows.map((r) => r.changeType)).toEqual([
      'deleted',
      'modified',
      'added',
    ]);
  });

  it('builds a stable-id → change-type lookup for scene colouring', () => {
    const g = groupModelDiff(makeDiff());
    expect(g.changeByStableId.get('a1')).toBe('added');
    expect(g.changeByStableId.get('d1e')).toBe('deleted');
    expect(g.changeByStableId.get('m1')).toBe('modified');
    expect(g.changeByStableId.size).toBe(5);
  });

  it('mirrors the summary totals verbatim (no recompute)', () => {
    const g = groupModelDiff(makeDiff());
    expect(g.totals).toEqual({ added: 2, deleted: 1, modified: 2 });
  });

  it('formats per-field deltas for modified entries', () => {
    const g = groupModelDiff(makeDiff());
    const walls = g.groups.find((x) => x.category === 'Walls')!;
    const m1 = walls.rows.find((r) => r.stableId === 'm1')!;
    expect(m1.fieldDeltas).toHaveLength(2);
    const qty = m1.fieldDeltas.find((d) => d.field === 'quantities')!;
    expect(qty.oldText).toBe('{"area":10}');
    expect(qty.newText).toBe('{"area":12}');
  });

  it('falls back to Uncategorised when element_type is empty', () => {
    const diff = makeDiff();
    diff.diff_details!.added.push({
      stable_id: 'a3',
      element_type: null,
      name: 'Mystery',
    });
    const g = groupModelDiff(diff);
    expect(g.groups.some((x) => x.category === 'Uncategorised')).toBe(true);
  });

  it('handles a null diff_details gracefully', () => {
    const diff = makeDiff();
    diff.diff_details = null;
    const g = groupModelDiff(diff);
    expect(g.groups).toEqual([]);
    expect(g.changeByStableId.size).toBe(0);
    // Summary still mirrored even with no detail rows.
    expect(g.totals.added).toBe(2);
  });
});

describe('diffGrouping.formatDiffValue', () => {
  it('renders nullish as an em-dash', () => {
    expect(formatDiffValue(null)).toBe('—');
    expect(formatDiffValue(undefined)).toBe('—');
    expect(formatDiffValue('')).toBe('—');
  });

  it('passes through scalars', () => {
    expect(formatDiffValue('Concrete')).toBe('Concrete');
    expect(formatDiffValue(42)).toBe('42');
    expect(formatDiffValue(true)).toBe('true');
  });

  it('JSON-encodes objects and truncates very long ones', () => {
    expect(formatDiffValue({ a: 1 })).toBe('{"a":1}');
    const big = formatDiffValue({ s: 'x'.repeat(500) });
    expect(big.endsWith('…')).toBe(true);
    expect(big.length).toBeLessThanOrEqual(120);
  });
});
