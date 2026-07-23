// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Unit tests for the pure inspection-tool helpers behind the point-cloud
 * viewer's cross-section, measure and clip-box features.
 */
import { describe, expect, it } from 'vitest';
import {
  angleAtVertex,
  annotationsToCsv,
  boxPlanes,
  buildCsv,
  chooseScaleBar,
  computeMeasurement3D,
  computePolylineMetrics,
  decimationStride,
  deriveCloudBounds,
  estimateVolumeVsPlane,
  formatAngle,
  formatAreaM2,
  formatLengthMm,
  formatMetersLabel,
  formatVolumeM3,
  heightSlicePlanes,
  isWithinPlanes,
  planeDistance,
  pointInPolygonXZ,
  polygonAreaXZ,
  polylineToCsv,
  presetViewOffset,
  scaleClipBox,
  slugifyForFilename,
  worldToScanCoords,
} from './pointcloudTools';

describe('computeMeasurement3D', () => {
  it('computes straight-line, horizontal and vertical spread', () => {
    const m = computeMeasurement3D({ x: 0, y: 0, z: 0 }, { x: 3, y: 4, z: 0 });
    expect(m.distance).toBeCloseTo(5, 6);
    expect(m.horizontal).toBeCloseTo(3, 6);
    expect(m.vertical).toBeCloseTo(4, 6);
  });

  it('handles a purely vertical measurement', () => {
    const m = computeMeasurement3D({ x: 1, y: 1, z: 1 }, { x: 1, y: 3.5, z: 1 });
    expect(m.distance).toBeCloseTo(2.5, 6);
    expect(m.horizontal).toBeCloseTo(0, 6);
    expect(m.vertical).toBeCloseTo(2.5, 6);
  });
});

describe('formatLengthMm', () => {
  it('renders sub-metre lengths as whole millimetres', () => {
    expect(formatLengthMm(0.1234)).toBe('123 mm');
    expect(formatLengthMm(0.0005)).toBe('1 mm');
  });

  it('renders metre-and-above lengths with two decimals', () => {
    expect(formatLengthMm(1)).toBe('1.00 m');
    expect(formatLengthMm(12.3456)).toBe('12.35 m');
  });

  it('falls back gracefully for non-finite input', () => {
    expect(formatLengthMm(Number.NaN)).toBe('-');
  });
});

describe('formatMetersLabel', () => {
  it('always renders two-decimal metres', () => {
    expect(formatMetersLabel(0.5)).toBe('0.50 m');
    expect(formatMetersLabel(-3)).toBe('-3.00 m');
  });
});

describe('deriveCloudBounds', () => {
  it('centres the bbox on the wire center and derives the diagonal', () => {
    const bounds = deriveCloudBounds({
      bboxMin: [-1, -2, 0],
      bboxMax: [9, 8, 10],
      center: [4, 3, 5],
    });
    expect(bounds.localMin).toEqual({ x: -5, y: -5, z: -5 });
    expect(bounds.localMax).toEqual({ x: 5, y: 5, z: 5 });
    expect(bounds.diagonal).toBeCloseTo(Math.sqrt(300), 6);
    expect(bounds.zMin).toBe(-5);
    expect(bounds.zMax).toBe(5);
  });

  it('maps local (x, y, z) to world (x, z, -y) for the rotated viewer frame', () => {
    const bounds = deriveCloudBounds({
      bboxMin: [0, 0, 0],
      bboxMax: [2, 4, 6],
      center: [0, 0, 0],
    });
    // local x in [0,2] -> world x in [0,2]
    expect(bounds.worldMin.x).toBe(0);
    expect(bounds.worldMax.x).toBe(2);
    // local z in [0,6] -> world y in [0,6]
    expect(bounds.worldMin.y).toBe(0);
    expect(bounds.worldMax.y).toBe(6);
    // local y in [0,4] -> world z in [-4,0]
    expect(bounds.worldMin.z).toBe(-4);
    expect(bounds.worldMax.z).toBe(0);
  });

  it('never returns a zero diagonal for a degenerate (point) cloud', () => {
    const bounds = deriveCloudBounds({ bboxMin: [1, 1, 1], bboxMax: [1, 1, 1], center: [1, 1, 1] });
    expect(bounds.diagonal).toBe(1);
  });
});

describe('heightSlicePlanes + boxPlanes + isWithinPlanes', () => {
  it('keeps points inside a height band and rejects points outside it', () => {
    const planes = heightSlicePlanes(1, 3);
    expect(isWithinPlanes({ x: 0, y: 2, z: 0 }, planes)).toBe(true);
    expect(isWithinPlanes({ x: 0, y: 0.5, z: 0 }, planes)).toBe(false);
    expect(isWithinPlanes({ x: 0, y: 3.5, z: 0 }, planes)).toBe(false);
  });

  it('keeps points inside an axis-aligned box and rejects points outside it', () => {
    const planes = boxPlanes({ min: { x: -1, y: -1, z: -1 }, max: { x: 1, y: 1, z: 1 } });
    expect(planes).toHaveLength(6);
    expect(isWithinPlanes({ x: 0, y: 0, z: 0 }, planes)).toBe(true);
    expect(isWithinPlanes({ x: 2, y: 0, z: 0 }, planes)).toBe(false);
    expect(isWithinPlanes({ x: 0, y: 0, z: -2 }, planes)).toBe(false);
  });

  it('combines slice + box planes as an intersection (AND), not a union', () => {
    const planes = [
      ...heightSlicePlanes(0, 10),
      ...boxPlanes({ min: { x: -1, y: -1, z: -1 }, max: { x: 1, y: 1, z: 1 } }),
    ];
    // Y = 0.5 satisfies both the slice band [0,10] and the box's Y range
    // [-1,1], isolating X as the only reason this point should fail.
    expect(isWithinPlanes({ x: 5, y: 0.5, z: 0 }, planes)).toBe(false);
    // Inside both the slice band and the box on every axis.
    expect(isWithinPlanes({ x: 0, y: 0.5, z: 0 }, planes)).toBe(true);
  });

  it('planeDistance is signed and zero exactly on the plane', () => {
    const [minPlane] = heightSlicePlanes(2, 8);
    expect(planeDistance({ x: 0, y: 2, z: 0 }, minPlane)).toBeCloseTo(0, 6);
    expect(planeDistance({ x: 0, y: 5, z: 0 }, minPlane)).toBeCloseTo(3, 6);
  });
});

describe('scaleClipBox', () => {
  const fullBox = { min: { x: -10, y: -10, z: -10 }, max: { x: 10, y: 10, z: 10 } };

  it('grows a box around its centre without exceeding the full bounds', () => {
    const box = { min: { x: -1, y: -1, z: -1 }, max: { x: 1, y: 1, z: 1 } };
    const grown = scaleClipBox(box, 5, fullBox, 0.01);
    expect(grown.min.x).toBe(-5);
    expect(grown.max.x).toBe(5);
    // Growing further should clamp to the full bounds, not overshoot them.
    const grownAgain = scaleClipBox(grown, 10, fullBox, 0.01);
    expect(grownAgain.min.x).toBe(-10);
    expect(grownAgain.max.x).toBe(10);
  });

  it('shrinks a box around its centre without collapsing past the minimum half-extent', () => {
    const box = { min: { x: -4, y: -4, z: -4 }, max: { x: 4, y: 4, z: 4 } };
    const shrunk = scaleClipBox(box, 0.1, fullBox, 1);
    expect(shrunk.min.x).toBeCloseTo(-1, 6);
    expect(shrunk.max.x).toBeCloseTo(1, 6);
  });

  it('preserves an off-centre box position while scaling', () => {
    const box = { min: { x: 2, y: 2, z: 2 }, max: { x: 4, y: 4, z: 4 } };
    const grown = scaleClipBox(box, 2, fullBox, 0.01);
    // centre stays at 3, half-extent doubles from 1 to 2.
    expect(grown.min.x).toBe(1);
    expect(grown.max.x).toBe(5);
  });
});

describe('slugifyForFilename', () => {
  it('lower-cases and hyphenates a scan label', () => {
    expect(slugifyForFilename('Ground Floor Scan')).toBe('ground-floor-scan');
  });

  it('strips punctuation and collapses repeated separators', () => {
    expect(slugifyForFilename('  Roof -- North!! ')).toBe('roof-north');
  });

  it('falls back to "scan" when nothing usable survives', () => {
    expect(slugifyForFilename('***')).toBe('scan');
    expect(slugifyForFilename('')).toBe('scan');
  });
});

describe('computePolylineMetrics', () => {
  it('returns zeros with a null last segment for empty or single-point paths', () => {
    for (const pts of [[], [{ x: 1, y: 2, z: 3 }]]) {
      const m = computePolylineMetrics(pts);
      expect(m.totalLength).toBe(0);
      expect(m.segmentCount).toBe(0);
      expect(m.lastSegment).toBeNull();
      expect(m.straightLine).toBe(0);
    }
  });

  it('matches the single-segment measurement for a two-point path', () => {
    const m = computePolylineMetrics([
      { x: 0, y: 0, z: 0 },
      { x: 3, y: 4, z: 0 },
    ]);
    expect(m.segmentCount).toBe(1);
    expect(m.totalLength).toBeCloseTo(5, 6);
    expect(m.straightLine).toBeCloseTo(5, 6);
    expect(m.lastSegment?.distance).toBeCloseTo(5, 6);
    expect(m.lastSegment?.vertical).toBeCloseTo(4, 6);
  });

  it('sums every segment and reports the final segment separately', () => {
    // An L-shape: 3 m east, then 4 m up. Total 7, straight-line 5.
    const m = computePolylineMetrics([
      { x: 0, y: 0, z: 0 },
      { x: 3, y: 0, z: 0 },
      { x: 3, y: 4, z: 0 },
    ]);
    expect(m.segmentCount).toBe(2);
    expect(m.totalLength).toBeCloseTo(7, 6);
    expect(m.straightLine).toBeCloseTo(5, 6);
    // Last segment is the vertical 4 m leg.
    expect(m.lastSegment?.distance).toBeCloseTo(4, 6);
    expect(m.lastSegment?.vertical).toBeCloseTo(4, 6);
    expect(m.lastSegment?.horizontal).toBeCloseTo(0, 6);
  });
});

describe('polygonAreaXZ', () => {
  it('returns 0 for degenerate polygons of fewer than three vertices', () => {
    expect(polygonAreaXZ([])).toBe(0);
    expect(polygonAreaXZ([{ x: 0, y: 0, z: 0 }])).toBe(0);
    expect(polygonAreaXZ([{ x: 0, y: 0, z: 0 }, { x: 1, y: 0, z: 1 }])).toBe(0);
  });

  it('computes the area of a unit square on the X/Z plane, ignoring height', () => {
    const square = [
      { x: 0, y: 5, z: 0 },
      { x: 2, y: 9, z: 0 },
      { x: 2, y: 1, z: 2 },
      { x: 0, y: 7, z: 2 },
    ];
    expect(polygonAreaXZ(square)).toBeCloseTo(4, 6);
  });

  it('is winding-order independent (absolute area)', () => {
    const cw = [
      { x: 0, y: 0, z: 0 },
      { x: 0, y: 0, z: 3 },
      { x: 3, y: 0, z: 3 },
      { x: 3, y: 0, z: 0 },
    ];
    expect(polygonAreaXZ(cw)).toBeCloseTo(9, 6);
  });
});

describe('pointInPolygonXZ', () => {
  const square = [
    { x: 0, y: 0, z: 0 },
    { x: 4, y: 0, z: 0 },
    { x: 4, y: 0, z: 4 },
    { x: 0, y: 0, z: 4 },
  ];

  it('detects points inside and outside a square footprint', () => {
    expect(pointInPolygonXZ({ x: 2, z: 2 }, square)).toBe(true);
    expect(pointInPolygonXZ({ x: 5, z: 2 }, square)).toBe(false);
    expect(pointInPolygonXZ({ x: -1, z: 2 }, square)).toBe(false);
  });

  it('returns false for a degenerate polygon', () => {
    expect(pointInPolygonXZ({ x: 0, z: 0 }, [])).toBe(false);
    expect(pointInPolygonXZ({ x: 0, z: 0 }, square.slice(0, 2))).toBe(false);
  });
});

describe('estimateVolumeVsPlane', () => {
  const square = [
    { x: 0, y: 0, z: 0 },
    { x: 2, y: 0, z: 0 },
    { x: 2, y: 0, z: 2 },
    { x: 0, y: 0, z: 2 },
  ];

  // Fill a 2x2 footprint with samples at height y = 1, one per 1 m cell.
  const flatSamples = [
    { x: 0.5, y: 1, z: 0.5 },
    { x: 1.5, y: 1, z: 0.5 },
    { x: 0.5, y: 1, z: 1.5 },
    { x: 1.5, y: 1, z: 1.5 },
  ];

  it('estimates a flat slab volume as area x height above the reference plane', () => {
    const v = estimateVolumeVsPlane(flatSamples, square, 0, 1);
    expect(v.cellCount).toBe(4);
    expect(v.area).toBeCloseTo(4, 6);
    // 4 cells x 1 m2 x 1 m height = 4 m3 of fill, no cut.
    expect(v.fill).toBeCloseTo(4, 6);
    expect(v.cut).toBeCloseTo(0, 6);
    expect(v.net).toBeCloseTo(4, 6);
  });

  it('splits fill and cut around the reference elevation', () => {
    const mixed = [
      { x: 0.5, y: 2, z: 0.5 }, // +2 above ref 0 -> fill
      { x: 1.5, y: -1, z: 1.5 }, // -1 below ref 0 -> cut
    ];
    const v = estimateVolumeVsPlane(mixed, square, 0, 1);
    expect(v.fill).toBeCloseTo(2, 6);
    expect(v.cut).toBeCloseTo(1, 6);
    expect(v.net).toBeCloseTo(1, 6);
  });

  it('ignores samples outside the polygon footprint', () => {
    const withStray = [...flatSamples, { x: 9, y: 100, z: 9 }];
    const v = estimateVolumeVsPlane(withStray, square, 0, 1);
    expect(v.cellCount).toBe(4);
    expect(v.fill).toBeCloseTo(4, 6);
  });

  it('guards degenerate input (empty, bad cell size, non-finite reference)', () => {
    expect(estimateVolumeVsPlane([], square, 0, 1).net).toBe(0);
    expect(estimateVolumeVsPlane(flatSamples, square, 0, 0).cellCount).toBe(0);
    expect(estimateVolumeVsPlane(flatSamples, square, Number.NaN, 1).fill).toBe(0);
    expect(estimateVolumeVsPlane(flatSamples, square.slice(0, 2), 0, 1).net).toBe(0);
  });

  it('skips samples carrying non-finite coordinates', () => {
    const withNaN = [...flatSamples, { x: Number.NaN, y: 1, z: 1 }];
    const v = estimateVolumeVsPlane(withNaN, square, 0, 1);
    expect(v.cellCount).toBe(4);
  });
});

describe('worldToScanCoords', () => {
  it('undoes the viewer rotation and re-adds the wire center', () => {
    // Forward mapping local (x, y, z) -> world (x, z, -y). Pick a local point,
    // roll it forward by hand, then confirm the inverse recovers scan coords.
    const center: [number, number, number] = [100, 200, 300];
    const local = { x: 1, y: 2, z: 3 };
    const world = { x: local.x, y: local.z, z: -local.y }; // (1, 3, -2)
    const scan = worldToScanCoords(world, center);
    expect(scan.x).toBeCloseTo(local.x + center[0], 6);
    expect(scan.y).toBeCloseTo(local.y + center[1], 6);
    expect(scan.z).toBeCloseTo(local.z + center[2], 6);
  });

  it('returns the local frame unchanged when the center is the origin', () => {
    const scan = worldToScanCoords({ x: 5, y: 6, z: -7 }, [0, 0, 0]);
    expect(scan).toEqual({ x: 5, y: 7, z: 6 });
  });
});

describe('presetViewOffset', () => {
  it('places the top view mostly overhead with a small anti-gimbal tilt', () => {
    const o = presetViewOffset('top', 10);
    expect(o.y).toBe(10);
    expect(o.z).toBe(0);
    expect(o.x).toBeGreaterThan(0);
    expect(o.x).toBeLessThan(1);
  });

  it('aligns front and side views to single axes', () => {
    expect(presetViewOffset('front', 8)).toEqual({ x: 0, y: 0, z: 8 });
    expect(presetViewOffset('side', 8)).toEqual({ x: 8, y: 0, z: 0 });
  });

  it('offsets the iso view on all three axes', () => {
    const o = presetViewOffset('iso', 10);
    expect(o.x).toBeGreaterThan(0);
    expect(o.y).toBeGreaterThan(0);
    expect(o.z).toBeGreaterThan(0);
  });

  it('falls back to a unit distance for non-positive or non-finite input', () => {
    expect(presetViewOffset('side', 0)).toEqual({ x: 1, y: 0, z: 0 });
    expect(presetViewOffset('front', Number.NaN)).toEqual({ x: 0, y: 0, z: 1 });
  });
});

describe('decimationStride', () => {
  it('keeps every point at full fraction', () => {
    expect(decimationStride(1000, 1)).toBe(1);
    expect(decimationStride(1000, 2)).toBe(1);
  });

  it('derives an integer stride from the keep fraction', () => {
    expect(decimationStride(1000, 0.5)).toBe(2);
    expect(decimationStride(1000, 0.25)).toBe(4);
    expect(decimationStride(1000, 0.1)).toBe(10);
  });

  it('collapses to the point count for a zero or negative fraction', () => {
    expect(decimationStride(1000, 0)).toBe(1000);
    expect(decimationStride(1000, -0.5)).toBe(1000);
  });

  it('never returns less than 1 and tolerates tiny clouds', () => {
    expect(decimationStride(1, 0.5)).toBe(1);
    expect(decimationStride(0, 0.5)).toBe(1);
    expect(decimationStride(Number.NaN, 0.5)).toBe(1);
  });
});

describe('formatAreaM2 + formatVolumeM3', () => {
  it('renders two-decimal ASCII units', () => {
    expect(formatAreaM2(12.345)).toBe('12.35 m2');
    expect(formatVolumeM3(5.5)).toBe('5.50 m3');
  });

  it('falls back gracefully for non-finite input', () => {
    expect(formatAreaM2(Number.NaN)).toBe('-');
    expect(formatVolumeM3(Number.POSITIVE_INFINITY)).toBe('-');
  });
});

describe('buildCsv', () => {
  it('joins headers and rows, escaping commas, quotes and newlines', () => {
    const csv = buildCsv(
      ['a', 'b'],
      [
        [1, 'x,y'],
        ['q"e', 'line\nbreak'],
      ],
    );
    expect(csv).toBe('a,b\n1,"x,y"\n"q""e","line\nbreak"');
  });

  it('emits just the header line for empty rows', () => {
    expect(buildCsv(['one', 'two'], [])).toBe('one,two');
  });
});

describe('annotationsToCsv', () => {
  it('serialises pins with note and both coordinate frames', () => {
    const csv = annotationsToCsv([
      {
        index: 1,
        note: 'crack',
        scan: { x: 10.1234, y: 20, z: 30 },
        world: { x: 1, y: 2, z: 3 },
      },
    ]);
    const [header, row] = csv.split('\n');
    expect(header).toBe('index,note,scan_x,scan_y,scan_z,view_x,view_y,view_z');
    expect(row).toBe('1,crack,10.123,20,30,1,2,3');
  });

  it('quotes a note containing a comma', () => {
    const csv = annotationsToCsv([
      { index: 2, note: 'spall, east face', scan: { x: 0, y: 0, z: 0 }, world: { x: 0, y: 0, z: 0 } },
    ]);
    expect(csv.split('\n')[1]).toContain('"spall, east face"');
  });
});

describe('polylineToCsv', () => {
  it('reports per-vertex scan coordinates plus segment and cumulative length', () => {
    const csv = polylineToCsv(
      [
        { x: 0, y: 0, z: 0 },
        { x: 3, y: 0, z: 0 },
        { x: 3, y: 0, z: 4 },
      ],
      [0, 0, 0],
    );
    const rows = csv.split('\n');
    expect(rows[0]).toBe('vertex,scan_x,scan_y,scan_z,segment_m,cumulative_m');
    // First vertex has a zero segment and cumulative.
    expect(rows[1]).toBe('1,0,0,0,0,0');
    // Second vertex: 3 m segment, 3 m cumulative.
    expect(rows[2]?.endsWith('3,3')).toBe(true);
    // Third vertex: 4 m segment, 7 m cumulative.
    expect(rows[3]?.endsWith('4,7')).toBe(true);
  });
});

describe('angleAtVertex', () => {
  it('reads a right angle at the middle vertex', () => {
    // Rays along +X and +Z from the origin meet at 90 degrees.
    const deg = angleAtVertex({ x: 1, y: 0, z: 0 }, { x: 0, y: 0, z: 0 }, { x: 0, y: 0, z: 1 });
    expect(deg).toBeCloseTo(90, 6);
  });

  it('reads a straight (180 degree) angle', () => {
    const deg = angleAtVertex({ x: -2, y: 0, z: 0 }, { x: 0, y: 0, z: 0 }, { x: 5, y: 0, z: 0 });
    expect(deg).toBeCloseTo(180, 6);
  });

  it('reads an acute angle and is scale-invariant', () => {
    // 45 degrees between +X and the X/Z diagonal, regardless of ray length.
    const deg = angleAtVertex({ x: 3, y: 0, z: 0 }, { x: 0, y: 0, z: 0 }, { x: 7, y: 0, z: 7 });
    expect(deg).toBeCloseTo(45, 6);
  });

  it('measures a roof pitch off the vertical rise and horizontal run', () => {
    // Ridge apex at (0, 3) with eaves 4 m out each side: each slope is
    // atan(3/4) ~ 36.87 deg from horizontal, so the apex angle is ~106.26 deg.
    const apex = { x: 0, y: 3, z: 0 };
    const deg = angleAtVertex({ x: -4, y: 0, z: 0 }, apex, { x: 4, y: 0, z: 0 });
    expect(deg).toBeCloseTo(2 * (90 - (Math.atan2(3, 4) * 180) / Math.PI), 4);
  });

  it('returns NaN for a degenerate (coincident) vertex', () => {
    expect(angleAtVertex({ x: 0, y: 0, z: 0 }, { x: 0, y: 0, z: 0 }, { x: 1, y: 0, z: 0 })).toBeNaN();
  });
});

describe('formatAngle', () => {
  it('renders one decimal with a degree glyph', () => {
    expect(formatAngle(90)).toBe('90.0°');
    expect(formatAngle(36.8699)).toBe('36.9°');
  });

  it('falls back gracefully for non-finite input', () => {
    expect(formatAngle(Number.NaN)).toBe('-');
    expect(formatAngle(Number.POSITIVE_INFINITY)).toBe('-');
  });
});

describe('chooseScaleBar', () => {
  it('picks the largest 1/2/5 x 10^n length that fits the allotted width', () => {
    // 0.05 m per pixel over 120 px = 6 m of headroom -> a 5 m bar (100 px).
    const bar = chooseScaleBar(0.05, 120);
    expect(bar.meters).toBe(5);
    expect(bar.pixels).toBeCloseTo(100, 6);
    expect(bar.label).toBe('5 m');
  });

  it('drops into a 2 m bar when 5 m no longer fits', () => {
    // 0.05 m/px over 80 px = 4 m headroom -> 2 m (5 m would be 100 px, too wide).
    const bar = chooseScaleBar(0.05, 80);
    expect(bar.meters).toBe(2);
    expect(bar.pixels).toBeCloseTo(40, 6);
    expect(bar.label).toBe('2 m');
  });

  it('labels sub-metre bars in centimetres', () => {
    // 0.005 m/px over 120 px = 0.6 m headroom -> a 0.5 m (50 cm) bar.
    const bar = chooseScaleBar(0.005, 120);
    expect(bar.meters).toBeCloseTo(0.5, 6);
    expect(bar.label).toBe('50 cm');
  });

  it('labels kilometre-scale bars in km', () => {
    // 20 m/px over 120 px = 2400 m headroom -> a 2 km bar.
    const bar = chooseScaleBar(20, 120);
    expect(bar.meters).toBe(2000);
    expect(bar.label).toBe('2 km');
  });

  it('never draws wider than the allotted pixels', () => {
    for (const wpp of [0.001, 0.02, 0.5, 3, 50]) {
      const bar = chooseScaleBar(wpp, 100);
      expect(bar.pixels).toBeLessThanOrEqual(100 + 1e-9);
      expect(bar.pixels).toBeGreaterThan(0);
    }
  });

  it('guards non-positive or non-finite input', () => {
    expect(chooseScaleBar(0, 100)).toEqual({ meters: 0, pixels: 0, label: '-' });
    expect(chooseScaleBar(-1, 100)).toEqual({ meters: 0, pixels: 0, label: '-' });
    expect(chooseScaleBar(0.05, 0)).toEqual({ meters: 0, pixels: 0, label: '-' });
    expect(chooseScaleBar(Number.NaN, 100)).toEqual({ meters: 0, pixels: 0, label: '-' });
  });
});
