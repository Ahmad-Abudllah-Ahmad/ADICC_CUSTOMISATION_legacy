// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, expect, it } from 'vitest';
import {
  buildClashBimLink,
  parseClashDeepLink,
  clashCentroidToViewerSpace,
} from '../clashBimLink';

describe('buildClashBimLink', () => {
  it('isolates BOTH elements, flags clash, and passes the raw centroid', () => {
    const link = buildClashBimLink({
      projectId: '0cefc29a-4e20-4287-be24-8ea0c2e4343b',
      modelId: '6eb959f4-4450-4a45-89fc-753f06ba6dbc',
      aElementId: '181f0c0b-457f-4fdd-aeae-19b0af4d0cb0',
      bElementId: '753d1b91-98e1-442c-a74e-830b988cba3f',
      cx: 11.227,
      cy: 6.1682,
      cz: 3.995,
    });
    const [path, query] = link.split('?');
    expect(path).toBe(
      '/projects/0cefc29a-4e20-4287-be24-8ea0c2e4343b/bim/6eb959f4-4450-4a45-89fc-753f06ba6dbc',
    );
    const p = new URLSearchParams(query);
    // Both interfering elements must be isolated (the original bug isolated
    // nothing visible because only single-element selection was wired).
    expect(p.get('isolate')).toBe(
      '181f0c0b-457f-4fdd-aeae-19b0af4d0cb0,753d1b91-98e1-442c-a74e-830b988cba3f',
    );
    expect(p.get('clash')).toBe('1');
    expect(p.get('focus')).toBe('11.227,6.1682,3.995');
  });

  it('omits focus when the centroid is not finite', () => {
    const link = buildClashBimLink({
      projectId: 'p',
      modelId: 'm',
      aElementId: 'a',
      bElementId: 'b',
      cx: Number.NaN,
      cy: 0,
      cz: 0,
    });
    const p = new URLSearchParams(link.split('?')[1]);
    expect(p.has('focus')).toBe(false);
    expect(p.get('isolate')).toBe('a,b');
  });

  it('falls back to a bare model link when both ids are empty', () => {
    expect(
      buildClashBimLink({
        projectId: 'p',
        modelId: 'm',
        aElementId: '',
        bElementId: '',
        cx: 1,
        cy: 2,
        cz: 3,
      }),
    ).toBe('/projects/p/bim/m');
  });
});

describe('parseClashDeepLink', () => {
  it('round-trips a built clash link', () => {
    const link = buildClashBimLink({
      projectId: 'p',
      modelId: 'm',
      aElementId: 'uuid-a',
      bElementId: 'uuid-b',
      cx: 11.227,
      cy: 6.1682,
      cz: 3.995,
    });
    const parsed = parseClashDeepLink(
      new URLSearchParams(link.split('?')[1]),
    );
    expect(parsed.ids).toEqual(['uuid-a', 'uuid-b']);
    expect(parsed.isClash).toBe(true);
    expect(parsed.focus).toEqual({ x: 11.227, y: 6.1682, z: 3.995 });
  });

  it('treats a non-clash isolate link as not-clash with no focus', () => {
    const parsed = parseClashDeepLink(
      new URLSearchParams('isolate=x,y'),
    );
    expect(parsed.ids).toEqual(['x', 'y']);
    expect(parsed.isClash).toBe(false);
    expect(parsed.focus).toBeNull();
  });

  it('rejects a malformed focus (wrong arity / NaN)', () => {
    expect(
      parseClashDeepLink(new URLSearchParams('isolate=a&clash=1&focus=1,2'))
        .focus,
    ).toBeNull();
    expect(
      parseClashDeepLink(
        new URLSearchParams('isolate=a&clash=1&focus=1,foo,3'),
      ).focus,
    ).toBeNull();
  });

  it('returns an empty id list (not a [""], which would never match)', () => {
    expect(parseClashDeepLink(new URLSearchParams('')).ids).toEqual([]);
    expect(parseClashDeepLink(new URLSearchParams('isolate=')).ids).toEqual(
      [],
    );
  });
});

describe('clashCentroidToViewerSpace', () => {
  it('applies the Z-up → Y-up rotation the loaded scene uses', () => {
    // -90° about X maps (x, y, z) → (x, z, -y). This is the exact transform
    // ElementManager applies to element bbox centres, so the camera target
    // lands on the geometry rather than 90° off.
    expect(
      clashCentroidToViewerSpace({ x: 11.227, y: 6.1682, z: 3.995 }),
    ).toEqual({ x: 11.227, y: 3.995, z: -6.1682 });
  });

  it('keeps a point on the X axis fixed in X', () => {
    expect(clashCentroidToViewerSpace({ x: 5, y: 0, z: 0 })).toEqual({
      x: 5,
      y: 0,
      z: -0,
    });
  });
});
