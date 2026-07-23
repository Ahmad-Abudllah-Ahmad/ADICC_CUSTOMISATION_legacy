// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Pure viewport-math tests for the PDF takeoff viewer: clamp, fit, zoom-to-
 * selection, zoom-at-cursor re-anchor, ortho snap and the live draw readout.
 *
 * These pin the geometry the viewer wires into its toolbar / wheel / draw
 * paths so a refactor of the (large) viewer module cannot silently change
 * how a page fits, how a 45-degree drag snaps, or what the running-length
 * HUD reports.
 */
import { describe, it, expect } from 'vitest';
import {
  ZOOM_MIN,
  ZOOM_MAX,
  FIT_PADDING_PX,
  FIT_ZOOM_MIN,
  DUP_VERTEX_SCREEN_PX,
  VERTEX_SNAP_SCREEN_PX,
  clampZoom,
  computeFitZoom,
  boundingBoxOfPoints,
  mergeBoundingBoxes,
  computeZoomToBox,
  zoomAtCursorScroll,
  wheelZoomStep,
  orthoSnap,
  orthoSnapVertexDrag,
  dropTrailingDuplicateVertex,
  snapToVertex,
  computeDrawReadout,
} from '@/features/takeoff/lib/takeoff-viewport';
import type { ScaleConfig } from '@/modules/pdf-takeoff/data/scale-helpers';
import type { Point } from '@/features/takeoff/lib/takeoff-types';

/** 1:50 at 72dpi → 56.69 px/m, the viewer's canonical preset (see
 *  scale-helpers presetScale). A 50 px segment is therefore ~0.882 m. */
const SCALE_1_50: ScaleConfig = { pixelsPerUnit: 72 / (0.0254 * 50), unitLabel: 'm' };
const UNCALIBRATED: ScaleConfig = { pixelsPerUnit: 0, unitLabel: 'm', invalid: true };

describe('clampZoom', () => {
  it('clamps to [ZOOM_MIN, ZOOM_MAX]', () => {
    expect(clampZoom(10)).toBe(ZOOM_MAX);
    expect(clampZoom(0.01)).toBe(ZOOM_MIN);
    expect(clampZoom(1)).toBe(1);
  });

  it('quantizes to whole percent (no float drift)', () => {
    expect(clampZoom(1.23456)).toBe(1.23);
    expect(clampZoom(0.3333333)).toBe(0.33);
  });

  it('falls back to 1 for non-finite input', () => {
    expect(clampZoom(NaN)).toBe(1);
    // Infinity / -Infinity are non-finite, so they also take the safe
    // fallback rather than the clamp bounds.
    expect(clampZoom(Infinity)).toBe(1);
    expect(clampZoom(-Infinity)).toBe(1);
  });
});

describe('computeFitZoom', () => {
  it('fit-to-width uses the width ratio (minus padding)', () => {
    // page 1000 wide, viewport 600 wide → (600 - 32) / 1000 = 0.568
    const z = computeFitZoom(1000, 1400, 600, 800, 'width');
    expect(z).toBeCloseTo((600 - FIT_PADDING_PX * 2) / 1000, 2);
  });

  it('fit-to-page is the tighter of width / height', () => {
    // Tall page: height constrains. page 1000x2000, viewport 600x800.
    const widthZoom = (600 - FIT_PADDING_PX * 2) / 1000; // 0.568
    const heightZoom = (800 - FIT_PADDING_PX * 2) / 2000; // 0.384
    const z = computeFitZoom(1000, 2000, 600, 800, 'page');
    expect(z).toBeCloseTo(Math.min(widthZoom, heightZoom), 2);
    expect(z).toBeCloseTo(heightZoom, 2);
  });

  it('fit-to-page on a wide page is width-constrained', () => {
    const widthZoom = (600 - FIT_PADDING_PX * 2) / 4000;
    const z = computeFitZoom(4000, 500, 600, 800, 'page');
    expect(z).toBeCloseTo(widthZoom, 2);
  });

  it('result is clamped to the fit range (max ZOOM_MAX, floor FIT_ZOOM_MIN)', () => {
    // Tiny page in a huge viewport would over-zoom; clamp at max.
    expect(computeFitZoom(10, 10, 5000, 5000, 'width')).toBe(ZOOM_MAX);
    // A pathologically huge page under-zooms past any useful level; a fit
    // floors at FIT_ZOOM_MIN, NOT the manual ZOOM_MIN, so a real large-format
    // sheet (which lands well above this floor) is still framed whole rather
    // than clipped at 25%.
    expect(computeFitZoom(100000, 100000, 100, 100, 'page')).toBe(FIT_ZOOM_MIN);
  });

  it('falls back to 1 for degenerate dimensions', () => {
    expect(computeFitZoom(0, 100, 600, 800, 'width')).toBe(1);
    expect(computeFitZoom(100, 100, 10, 800, 'page')).toBe(1); // viewport < padding
  });
});

describe('boundingBoxOfPoints / mergeBoundingBoxes', () => {
  it('computes the AABB of a point set', () => {
    const box = boundingBoxOfPoints([
      { x: 10, y: 5 },
      { x: 3, y: 20 },
      { x: 8, y: 1 },
    ]);
    expect(box).toEqual({ minX: 3, minY: 1, maxX: 10, maxY: 20 });
  });

  it('returns null for an empty set', () => {
    expect(boundingBoxOfPoints([])).toBeNull();
  });

  it('handles a single point (zero-area box)', () => {
    expect(boundingBoxOfPoints([{ x: 7, y: 9 }])).toEqual({
      minX: 7,
      minY: 9,
      maxX: 7,
      maxY: 9,
    });
  });

  it('merges several boxes into their union', () => {
    const merged = mergeBoundingBoxes([
      { minX: 0, minY: 0, maxX: 10, maxY: 10 },
      { minX: 5, minY: -5, maxX: 8, maxY: 30 },
    ]);
    expect(merged).toEqual({ minX: 0, minY: -5, maxX: 10, maxY: 30 });
  });

  it('merge returns null for no boxes', () => {
    expect(mergeBoundingBoxes([])).toBeNull();
  });
});

describe('computeZoomToBox', () => {
  it('frames a box with margin and centers it', () => {
    const box = { minX: 100, minY: 100, maxX: 300, maxY: 200 }; // 200 x 100
    const res = computeZoomToBox(box, 800, 600, { marginFraction: 0.15 });
    // Width ratio: 800 / (200 * 1.3) = 3.08 ; height ratio: 600 / (100 * 1.3) = 4.6.
    // Min → width-constrained ≈ 3.08, but clamped to ZOOM_MAX (4)? 3.08 < 4 so kept.
    expect(res.zoom).toBeCloseTo(800 / (200 * 1.3), 1);
    // Midpoint (200, 150) centered: scroll = mid*zoom - viewport/2.
    expect(res.scrollLeft).toBeCloseTo(200 * res.zoom - 400, 1);
    expect(res.scrollTop).toBeCloseTo(150 * res.zoom - 300, 1);
  });

  it('never returns negative scroll', () => {
    // A box near the origin would push scroll negative; clamp at 0.
    const box = { minX: 0, minY: 0, maxX: 5, maxY: 5 };
    const res = computeZoomToBox(box, 800, 600);
    expect(res.scrollLeft).toBeGreaterThanOrEqual(0);
    expect(res.scrollTop).toBeGreaterThanOrEqual(0);
  });

  it('degenerate (single-point) box uses the fallback zoom and recenters', () => {
    const box = { minX: 50, minY: 60, maxX: 50, maxY: 60 };
    const res = computeZoomToBox(box, 800, 600, { fallbackZoom: 2 });
    expect(res.zoom).toBe(2);
    expect(res.scrollLeft).toBeCloseTo(Math.max(0, 50 * 2 - 400), 5);
    expect(res.scrollTop).toBeCloseTo(Math.max(0, 60 * 2 - 300), 5);
  });

  it('clamps an overly tight box to ZOOM_MAX', () => {
    const box = { minX: 0, minY: 0, maxX: 2, maxY: 2 };
    const res = computeZoomToBox(box, 800, 600);
    expect(res.zoom).toBe(ZOOM_MAX);
  });
});

describe('zoomAtCursorScroll', () => {
  it('keeps the world point under the cursor stationary', () => {
    // At zoom 1, scroll 0, cursor 100px in → world point is at 100.
    // Zoom to 2: that world point should now sit at 200 in canvas space,
    // so to keep it under the cursor (still 100px in) scroll must be 100.
    const { scrollLeft, scrollTop } = zoomAtCursorScroll(1, 2, 0, 0, 100, 100);
    expect(scrollLeft).toBe(100);
    expect(scrollTop).toBe(100);
  });

  it('handles an existing scroll offset', () => {
    // scroll 50, cursor 150 → world offset 200; ratio 1.5 → 300 - 150 = 150.
    const { scrollLeft } = zoomAtCursorScroll(2, 3, 50, 0, 150, 0);
    expect(scrollLeft).toBe((50 + 150) * 1.5 - 150);
  });

  it('returns the same scroll when zoom does not change', () => {
    const res = zoomAtCursorScroll(2, 2, 33, 44, 10, 10);
    expect(res).toEqual({ scrollLeft: 33, scrollTop: 44 });
  });

  it('never returns negative scroll', () => {
    // Zooming out near the top-left would push scroll negative; clamp at 0.
    const { scrollLeft, scrollTop } = zoomAtCursorScroll(2, 1, 0, 0, 10, 10);
    expect(scrollLeft).toBeGreaterThanOrEqual(0);
    expect(scrollTop).toBeGreaterThanOrEqual(0);
  });
});

describe('wheelZoomStep', () => {
  it('wheel up (deltaY < 0) zooms in', () => {
    expect(wheelZoomStep(1, -1)).toBeCloseTo(1.1, 5);
  });

  it('wheel down (deltaY > 0) zooms out', () => {
    expect(wheelZoomStep(1, 1)).toBeCloseTo(clampZoom(1 / 1.1), 5);
  });

  it('respects the clamp bounds', () => {
    expect(wheelZoomStep(ZOOM_MAX, -1)).toBe(ZOOM_MAX);
    expect(wheelZoomStep(ZOOM_MIN, 1)).toBe(ZOOM_MIN);
  });
});

describe('orthoSnap', () => {
  const anchor: Point = { x: 100, y: 100 };

  it('snaps a near-horizontal drag to exactly horizontal', () => {
    const snapped = orthoSnap(anchor, { x: 200, y: 105 });
    expect(snapped.y).toBeCloseTo(100, 5); // y locked to anchor
    expect(snapped.x).toBeGreaterThan(100); // points right
  });

  it('snaps a near-vertical drag to exactly vertical', () => {
    const snapped = orthoSnap(anchor, { x: 103, y: 250 });
    expect(snapped.x).toBeCloseTo(100, 5);
    expect(snapped.y).toBeGreaterThan(100);
  });

  it('snaps a near-45 drag to a clean diagonal', () => {
    const snapped = orthoSnap(anchor, { x: 200, y: 190 });
    const dx = snapped.x - anchor.x;
    const dy = snapped.y - anchor.y;
    expect(Math.abs(dx)).toBeCloseTo(Math.abs(dy), 5); // |dx| == |dy| on a 45
  });

  it('preserves the full drag length along the snapped axis', () => {
    // A horizontal-ish drag of length 100 should land 100 to the right,
    // not be shrunk to the x-component of the original vector.
    const snapped = orthoSnap(anchor, { x: 196, y: 128 }); // len = 100
    const len = Math.hypot(snapped.x - anchor.x, snapped.y - anchor.y);
    expect(len).toBeCloseTo(100, 5);
  });

  it('returns the anchor for a zero-length drag', () => {
    expect(orthoSnap(anchor, { x: 100, y: 100 })).toEqual({ x: 100, y: 100 });
  });
});

describe('orthoSnapVertexDrag', () => {
  it('squares an open run endpoint against its single neighbour, keeping length', () => {
    // Endpoint (index 1) of an open two-point run, dragged near-horizontal.
    const pts: Point[] = [
      { x: 0, y: 0 },
      { x: 100, y: 5 },
    ];
    const r = orthoSnapVertexDrag(pts, 1, { x: 100, y: 5 }, false);
    expect(r.y).toBeCloseTo(0, 5); // locked onto the neighbour's horizontal
    expect(r.x).toBeGreaterThan(100);
    // Length preserved along the axis, not shrunk to the x-component.
    expect(Math.hypot(r.x, r.y)).toBeCloseTo(Math.hypot(100, 5), 4);
  });

  it('picks the closest of two neighbours for an interior vertex', () => {
    // Interior vertex (index 1) between (0,0) and (20,0); the cursor is nearest
    // to a 45-degree line from (0,0), so the result lands on that diagonal.
    const pts: Point[] = [
      { x: 0, y: 0 },
      { x: 4, y: 4 },
      { x: 20, y: 0 },
    ];
    const r = orthoSnapVertexDrag(pts, 1, { x: 4.5, y: 5 }, false);
    expect(r.x).toBeCloseTo(r.y, 5); // on the 45-degree axis from (0,0)
    expect(r.x).toBeGreaterThan(0);
  });

  it('uses the wraparound neighbour for the first vertex of a closed shape', () => {
    // Square, closed. Vertex 0 wraps to vertex 3 (0,10) and forward to (10,0).
    // A cursor near the left (vertical) edge squares onto x = 0.
    const square: Point[] = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 0, y: 10 },
    ];
    const r = orthoSnapVertexDrag(square, 0, { x: 0.5, y: 8 }, true);
    expect(r.x).toBeCloseTo(0, 5); // vertical from the wraparound neighbour (0,10)
  });

  it('has no wraparound neighbour for the first vertex of an open run', () => {
    // Same first vertex and cursor as the closed case, but open: the only
    // neighbour is (10,0), so there is no vertical (0,10) anchor. The cursor
    // squares onto the 45-degree diagonal from (10,0) instead of onto x = 0.
    const open: Point[] = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 0, y: 10 },
    ];
    const r = orthoSnapVertexDrag(open, 0, { x: 0.5, y: 8 }, false);
    expect(Math.abs(r.x - 10)).toBeCloseTo(Math.abs(r.y), 4); // 45 from (10,0)
    expect(r.x).toBeGreaterThan(0.9); // not the closed case's vertical (x = 0)
  });

  it('returns the cursor unchanged for degenerate input', () => {
    const cursor: Point = { x: 5, y: 5 };
    expect(orthoSnapVertexDrag([{ x: 1, y: 1 }], 0, cursor, false)).toEqual(cursor);
    const two: Point[] = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
    ];
    expect(orthoSnapVertexDrag(two, 5, cursor, false)).toEqual(cursor);
    expect(orthoSnapVertexDrag(two, -1, cursor, true)).toEqual(cursor);
  });
});

describe('dropTrailingDuplicateVertex', () => {
  it('drops a trailing vertex within the screen-space threshold (issue #298)', () => {
    const pts = [
      { x: 0, y: 0 },
      { x: 40, y: 0 },
      { x: 42, y: 0 }, // 2 PDF units from the previous vertex
    ];
    // At zoom 1: screen distance 2px < DUP_VERTEX_SCREEN_PX (6) -> dropped.
    expect(dropTrailingDuplicateVertex(pts, 1)).toEqual([
      { x: 0, y: 0 },
      { x: 40, y: 0 },
    ]);
  });

  it('measures in screen space, so a high zoom keeps a vertex a low zoom would drop', () => {
    const pts = [
      { x: 0, y: 0 },
      { x: 40, y: 0 },
      { x: 44, y: 0 }, // 4 PDF units apart
    ];
    // zoom 1: 4px < 6px -> dropped.
    expect(dropTrailingDuplicateVertex(pts, 1)).toHaveLength(2);
    // zoom 4: 16px >= 6px -> kept (the points are far apart on screen).
    expect(dropTrailingDuplicateVertex(pts, 4)).toHaveLength(3);
  });

  it('keeps meaningfully separated vertices (a right-click finish)', () => {
    const pts = [
      { x: 0, y: 0 },
      { x: 50, y: 0 },
      { x: 50, y: 60 },
    ];
    expect(dropTrailingDuplicateVertex(pts, 1)).toBe(pts); // unchanged reference
  });

  it('returns the input unchanged for fewer than two points', () => {
    expect(dropTrailingDuplicateVertex([], 1)).toEqual([]);
    const one = [{ x: 5, y: 5 }];
    expect(dropTrailingDuplicateVertex(one, 1)).toBe(one);
  });

  it('honours a custom screen radius', () => {
    const pts = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 15, y: 0 }, // 5 units
    ];
    expect(dropTrailingDuplicateVertex(pts, 1, DUP_VERTEX_SCREEN_PX)).toHaveLength(2); // 5 < 6
    expect(dropTrailingDuplicateVertex(pts, 1, 4)).toHaveLength(3); // 5 >= 4
  });
});

describe('snapToVertex', () => {
  const vertices: Point[] = [
    { x: 0, y: 0 },
    { x: 100, y: 100 },
    { x: 200, y: 50 },
  ];

  it('snaps to the nearest vertex within the screen-space radius', () => {
    // Cursor 4 PDF-units from (100,100); at zoom 2 that is 8 screen px < 10.
    const snapped = snapToVertex({ x: 102, y: 103 }, vertices, 2);
    expect(snapped).toEqual({ x: 100, y: 100 });
  });

  it('returns null when no vertex is within the radius', () => {
    // 20 PDF-units away at zoom 1 = 20 screen px > 10.
    expect(snapToVertex({ x: 120, y: 100 }, vertices, 1)).toBeNull();
  });

  it('applies the radius in screen space (zoom scales the catch distance)', () => {
    const cursor = { x: 108, y: 100 }; // 8 PDF-units from (100,100)
    // zoom 1: 8 screen px < 10 -> snaps.
    expect(snapToVertex(cursor, vertices, 1)).toEqual({ x: 100, y: 100 });
    // zoom 2: 16 screen px > 10 -> no snap.
    expect(snapToVertex(cursor, vertices, 2)).toBeNull();
  });

  it('picks the closest of several in-range vertices', () => {
    const near: Point[] = [
      { x: 100, y: 100 },
      { x: 103, y: 100 }, // closer to the cursor below
    ];
    const snapped = snapToVertex({ x: 104, y: 100 }, near, 1, VERTEX_SNAP_SCREEN_PX);
    expect(snapped).toEqual({ x: 103, y: 100 });
  });

  it('returns a fresh copy, never the source vertex reference', () => {
    const snapped = snapToVertex({ x: 0, y: 0 }, vertices, 1);
    expect(snapped).toEqual({ x: 0, y: 0 });
    expect(snapped).not.toBe(vertices[0]);
  });

  it('returns null for an empty vertex set or a non-positive zoom', () => {
    expect(snapToVertex({ x: 0, y: 0 }, [], 1)).toBeNull();
    expect(snapToVertex({ x: 0, y: 0 }, vertices, 0)).toBeNull();
  });
});

describe('computeDrawReadout', () => {
  it('reports the cursor coordinate rounded to 1 decimal', () => {
    const r = computeDrawReadout([], { x: 12.34, y: 56.78 }, SCALE_1_50);
    expect(r.cursor).toEqual({ x: 12.3, y: 56.8 });
  });

  it('no anchor yet → segment and total are null', () => {
    const r = computeDrawReadout([], { x: 10, y: 10 }, SCALE_1_50);
    expect(r.segment).toBeNull();
    expect(r.total).toBeNull();
    expect(r.unit).toBe('m');
  });

  it('one placed point → live segment length to cursor', () => {
    // 50 px at 1:50 (56.69 px/m) ≈ 0.882 m.
    const r = computeDrawReadout([{ x: 0, y: 0 }], { x: 50, y: 0 }, SCALE_1_50);
    expect(r.segment).toBeCloseTo(50 / SCALE_1_50.pixelsPerUnit, 6);
    // Total with one placed point equals the live segment.
    expect(r.total).toBeCloseTo(r.segment ?? 0, 6);
  });

  it('cumulative total sums placed edges plus the live segment', () => {
    // Placed: (0,0)->(0,30) = 30px. Live: (0,30)->(40,30) = 40px. Total 70px.
    const r = computeDrawReadout(
      [
        { x: 0, y: 0 },
        { x: 0, y: 30 },
      ],
      { x: 40, y: 30 },
      SCALE_1_50,
    );
    expect(r.segment).toBeCloseTo(40 / SCALE_1_50.pixelsPerUnit, 6);
    expect(r.total).toBeCloseTo(70 / SCALE_1_50.pixelsPerUnit, 6);
  });

  it('uncalibrated page → lengths null, unit empty (no misleading 0 m)', () => {
    const r = computeDrawReadout([{ x: 0, y: 0 }], { x: 50, y: 0 }, UNCALIBRATED);
    expect(r.segment).toBeNull();
    expect(r.total).toBeNull();
    expect(r.unit).toBe('');
    // Coordinates still report.
    expect(r.cursor).toEqual({ x: 50, y: 0 });
  });
});
