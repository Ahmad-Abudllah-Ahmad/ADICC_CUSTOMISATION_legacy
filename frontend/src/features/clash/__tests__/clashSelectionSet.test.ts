// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, expect, it } from 'vitest';
import { deriveSelectionSetFromFindings } from '../clashSelectionSet';
import { buildSelectionSetBimLink } from '../clashBimLink';
import type { ClashResult } from '../api';

/** Build a minimal ClashResult with only the fields the derivation reads,
 *  cast through unknown so the test isn't coupled to the full wire shape. */
function fixture(over: Partial<ClashResult>): ClashResult {
  return {
    a_element_id: '',
    b_element_id: '',
    a_model_id: 'model-1',
    b_model_id: 'model-1',
    cx: 0,
    cy: 0,
    cz: 0,
    ...over,
  } as unknown as ClashResult;
}

describe('deriveSelectionSetFromFindings', () => {
  it('unions both interfering elements of every finding, de-duplicated', () => {
    const sel = deriveSelectionSetFromFindings([
      fixture({ a_element_id: 'a', b_element_id: 'b' }),
      fixture({ a_element_id: 'b', b_element_id: 'c' }), // b repeats
      fixture({ a_element_id: 'c', b_element_id: 'd' }), // c repeats
    ]);
    // first-seen order, no duplicates
    expect(sel.elementIds).toEqual(['a', 'b', 'c', 'd']);
    expect(sel.findingCount).toBe(3);
  });

  it('drops blank / whitespace ids and counts only contributing findings', () => {
    const sel = deriveSelectionSetFromFindings([
      fixture({ a_element_id: '  ', b_element_id: '' }), // contributes nothing
      fixture({ a_element_id: ' x ', b_element_id: 'y' }), // trimmed
    ]);
    expect(sel.elementIds).toEqual(['x', 'y']);
    expect(sel.findingCount).toBe(1);
  });

  it('averages finite centroids and ignores non-finite ones', () => {
    const sel = deriveSelectionSetFromFindings([
      fixture({ a_element_id: 'a', cx: 0, cy: 0, cz: 0 }),
      fixture({ a_element_id: 'b', cx: 10, cy: 20, cz: 30 }),
      fixture({ a_element_id: 'c', cx: Number.NaN, cy: 1, cz: 1 }), // skipped
    ]);
    expect(sel.focus).toEqual({ x: 5, y: 10, z: 15 });
  });

  it('returns a null focus when no finding has a usable centroid', () => {
    const sel = deriveSelectionSetFromFindings([
      fixture({ a_element_id: 'a', cx: Number.NaN, cy: 0, cz: 0 }),
    ]);
    expect(sel.focus).toBeNull();
  });

  it('flags mixedModels and picks the model owning the most elements', () => {
    const sel = deriveSelectionSetFromFindings([
      fixture({ a_element_id: 'a', a_model_id: 'm1', b_element_id: 'b', b_model_id: 'm2' }),
      fixture({ a_element_id: 'c', a_model_id: 'm2', b_element_id: 'd', b_model_id: 'm2' }),
    ]);
    expect(sel.mixedModels).toBe(true);
    // m2 is referenced by 3 of the 4 elements, m1 by 1 → open m2
    expect(sel.modelId).toBe('m2');
  });

  it('is not mixed and opens the single model when all findings share one', () => {
    const sel = deriveSelectionSetFromFindings([
      fixture({ a_element_id: 'a', b_element_id: 'b', a_model_id: 'm1', b_model_id: 'm1' }),
    ]);
    expect(sel.mixedModels).toBe(false);
    expect(sel.modelId).toBe('m1');
  });

  it('degrades cleanly on an empty input', () => {
    const sel = deriveSelectionSetFromFindings([]);
    expect(sel).toEqual({
      elementIds: [],
      modelId: '',
      focus: null,
      mixedModels: false,
      findingCount: 0,
    });
  });

  it('feeds buildSelectionSetBimLink to produce a valid multi-isolate link', () => {
    const sel = deriveSelectionSetFromFindings([
      fixture({ a_element_id: 'a', b_element_id: 'b', cx: 1, cy: 2, cz: 3 }),
      fixture({ a_element_id: 'c', b_element_id: 'd', cx: 3, cy: 4, cz: 5 }),
    ]);
    const link = buildSelectionSetBimLink({
      projectId: 'proj',
      modelId: sel.modelId || 'model-1',
      elementIds: sel.elementIds,
      focus: sel.focus,
    });
    const [path, query] = link.split('?');
    expect(path).toBe('/projects/proj/bim/model-1');
    const p = new URLSearchParams(query);
    expect(p.get('isolate')).toBe('a,b,c,d');
    expect(p.get('clash')).toBe('1');
    expect(p.get('focus')).toBe('2,3,4');
  });
});
