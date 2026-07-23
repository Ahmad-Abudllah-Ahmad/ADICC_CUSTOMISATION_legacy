// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Tests for the B4 folder grouping helper used by SmartViewsPanel. Pure
 * function, so this is a fast unit test with no rendering.
 */
import { describe, it, expect } from 'vitest';
import { groupViewsByFolder } from '../SmartViewsPanel';
import type { SmartViewResponse } from '../types';

function view(id: string, folder: string | null): SmartViewResponse {
  return {
    id,
    scope_type: 'user',
    scope_id: 'u1',
    name: `view-${id}`,
    description: null,
    folder,
    rules: [],
    default_action: 'show_all',
    color_legend: null,
    created_by: 'u1',
    created_at: '2026-06-29T00:00:00Z',
    updated_at: '2026-06-29T00:00:00Z',
  };
}

describe('groupViewsByFolder', () => {
  it('puts ungrouped views first, then folders in natural order', () => {
    const groups = groupViewsByFolder([
      view('a', 'Zone B'),
      view('b', null),
      view('c', 'Zone A'),
      view('d', 'Zone B'),
      view('e', ''),
    ]);
    expect(groups.map((g) => g.folder)).toEqual([null, 'Zone A', 'Zone B']);
    // ungrouped bucket holds both the null and blank-folder views.
    expect(groups[0]!.views.map((v) => v.id).sort()).toEqual(['b', 'e']);
    expect(groups[2]!.views.map((v) => v.id).sort()).toEqual(['a', 'd']);
  });

  it('trims folder labels and folds blanks into ungrouped', () => {
    const groups = groupViewsByFolder([
      view('a', '  Fire safety  '),
      view('b', '   '),
    ]);
    expect(groups.map((g) => g.folder)).toEqual([null, 'Fire safety']);
  });

  it('returns no ungrouped bucket when every view has a folder', () => {
    const groups = groupViewsByFolder([view('a', 'F1'), view('b', 'F1')]);
    expect(groups).toHaveLength(1);
    expect(groups[0]!.folder).toBe('F1');
    expect(groups[0]!.views).toHaveLength(2);
  });

  it('returns an empty array for no views', () => {
    expect(groupViewsByFolder([])).toEqual([]);
  });
});
