// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Unit tests for the OverlaySidebar centroid helpers.
 *
 * Pure-function coverage only — DOM/Query/Cesium interactions are
 * exercised via the broader Playwright pass (qa-crawler) and the
 * existing CesiumViewer integration tests.
 */

import { describe, expect, it } from 'vitest';

import { overlayCentroid, tilesetCentroid } from '../OverlaySidebar';
import type { GeoRasterOverlay, Tileset } from '../types';

function makeOverlay(
  corners: [number, number][] | null,
): GeoRasterOverlay {
  return {
    id: 'o1',
    project_id: 'p1',
    name: 'sample',
    source_kind: 'pdf',
    source_blob_url: null,
    source_page: 1,
    raster_blob_url: null,
    raster_width_px: 100,
    raster_height_px: 100,
    corners_geojson: (corners ?? []) as [number, number][],
    rotation_deg: '0',
    opacity: '1',
    crop_polygon_geojson: null,
    z_order: 0,
    visible: true,
    created_by: null,
    metadata: {},
    created_at: '',
    updated_at: '',
  };
}

function makeTileset(bv: Record<string, unknown> | null): Tileset {
  return {
    id: 't1',
    project_id: 'p1',
    source_kind: 'bim_model',
    source_id: 'x',
    name: 'ts',
    bucket: 'b',
    prefix: 'p/',
    tileset_json_uri: 'https://example.test/ts.json',
    bounding_volume: bv,
    geometric_error: '10',
    tile_format: 'b3dm',
    tile_count: 1,
    total_bytes: 1,
    status: 'ready',
    generated_at: null,
    generation_job_id: null,
    metadata: {},
    created_at: '',
    updated_at: '',
  };
}

describe('overlayCentroid', () => {
  it('averages the four corners', () => {
    // NW, NE, SE, SW around (10, 50)
    const o = makeOverlay([
      [9, 51],
      [11, 51],
      [11, 49],
      [9, 49],
    ]);
    expect(overlayCentroid(o)).toEqual({ lat: 50, lon: 10 });
  });

  it('returns null when corners are missing', () => {
    const o = makeOverlay(null);
    expect(overlayCentroid(o)).toBeNull();
  });

  it('returns null when a corner is malformed', () => {
    const o = makeOverlay([
      [9, 51],
      [11, 51],
      [Number.NaN, 49],
      [9, 49],
    ]);
    expect(overlayCentroid(o)).toBeNull();
  });

  it('returns null when corners has the wrong length', () => {
    const o = makeOverlay([
      [9, 51],
      [11, 51],
    ]);
    expect(overlayCentroid(o)).toBeNull();
  });
});

describe('tilesetCentroid', () => {
  it('decodes a region bounding volume (radians → degrees)', () => {
    // region around the equator/Greenwich
    const bv = {
      region: [
        -0.01 * (Math.PI / 180), // west
        -0.01 * (Math.PI / 180), // south
        0.01 * (Math.PI / 180), //  east
        0.01 * (Math.PI / 180), //  north
        0, // minH
        100, // maxH
      ],
    };
    const c = tilesetCentroid(makeTileset(bv));
    expect(c).not.toBeNull();
    if (!c) return;
    expect(c.lat).toBeCloseTo(0, 5);
    expect(c.lon).toBeCloseTo(0, 5);
  });

  it('decodes a sphere bounding volume (ECEF metres → lat/lon)', () => {
    // Earth radius along the X axis = lon 0, lat 0
    const R = 6_378_137;
    const c = tilesetCentroid(makeTileset({ sphere: [R, 0, 0, 100] }));
    expect(c).not.toBeNull();
    if (!c) return;
    expect(c.lat).toBeCloseTo(0, 5);
    expect(c.lon).toBeCloseTo(0, 5);
  });

  it('returns null when bounding_volume is missing', () => {
    expect(tilesetCentroid(makeTileset(null))).toBeNull();
  });

  it('returns null for unknown bounding-volume shapes', () => {
    expect(
      tilesetCentroid(makeTileset({ box: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] })),
    ).toBeNull();
  });
});
