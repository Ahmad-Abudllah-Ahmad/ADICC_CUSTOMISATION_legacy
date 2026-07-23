// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * api.ts unit tests — verify the URL templates we build hit the right
 * backend endpoints. apiGet / apiPost / apiPatch / apiDelete are mocked.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/shared/lib/api', () => {
  return {
    apiGet: vi.fn(async (path: string) => ({ _mockGet: path })),
    apiPost: vi.fn(async (path: string, body: unknown) => ({
      _mockPost: path,
      _body: body,
    })),
    apiPatch: vi.fn(async (path: string, body: unknown) => ({
      _mockPatch: path,
      _body: body,
    })),
    apiDelete: vi.fn(async (path: string) => ({ _mockDelete: path })),
  };
});

import {
  cancelJob,
  createAnchor,
  createImageryLayer,
  createViewpoint,
  deleteAnchor,
  exportGeoJSON,
  generateTileset,
  getMapConfig,
  importGeoJSON,
  importKML,
  listAnchors,
  listImageryLayers,
  listJobs,
  listOverlays,
  listTerrainSources,
  listTilesets,
  listViewpoints,
} from '../api';

const PROJECT = '11111111-2222-3333-4444-555555555555';

afterEach(() => {
  vi.clearAllMocks();
});

describe('geo_hub api endpoints', () => {
  it('getMapConfig hits /map-config/{project_id}', async () => {
    const res = (await getMapConfig(PROJECT)) as unknown as Record<string, string>;
    expect(res._mockGet).toBe(`/v1/geo-hub/map-config/${PROJECT}`);
  });

  it('listAnchors uses ?project_id query', async () => {
    const res = (await listAnchors(PROJECT)) as unknown as Record<string, string>;
    expect(res._mockGet).toBe(`/v1/geo-hub/anchors/?project_id=${PROJECT}`);
  });

  it('createAnchor POSTs to /anchors/', async () => {
    const res = (await createAnchor({
      project_id: PROJECT,
      lat: '52.52',
      lon: '13.40',
    })) as unknown as { _mockPost: string };
    expect(res._mockPost).toBe('/v1/geo-hub/anchors/');
  });

  it('deleteAnchor uses DELETE on /anchors/{id}', async () => {
    const res = (await deleteAnchor('abc')) as unknown as Record<string, string>;
    expect(res._mockDelete).toBe('/v1/geo-hub/anchors/abc');
  });

  it('generateTileset POSTs to /tilesets/generate/', async () => {
    const res = (await generateTileset({
      project_id: PROJECT,
      source_kind: 'bim_model',
      source_id: 'src1',
    })) as unknown as { _mockPost: string };
    expect(res._mockPost).toBe('/v1/geo-hub/tilesets/generate/');
  });

  it('listTilesets builds query string', async () => {
    const res = (await listTilesets(PROJECT)) as unknown as Record<string, string>;
    expect(res._mockGet).toBe(`/v1/geo-hub/tilesets/?project_id=${PROJECT}`);
  });

  it('cancelJob POSTs to /jobs/{id}/cancel', async () => {
    const res = (await cancelJob('job1')) as unknown as Record<string, string>;
    expect(res._mockPost).toBe('/v1/geo-hub/jobs/job1/cancel');
  });

  it('listJobs sends state filter when supplied', async () => {
    const res = (await listJobs(PROJECT, 'running')) as unknown as Record<
      string, string
    >;
    expect(res._mockGet).toContain('state=running');
    expect(res._mockGet).toContain(`project_id=${PROJECT}`);
  });

  it('createImageryLayer POSTs to /imagery-layers/', async () => {
    const res = (await createImageryLayer({
      project_id: PROJECT,
      name: 'OSM',
      provider: 'osm',
      url_template: 'https://x/{z}/{x}/{y}',
    })) as unknown as { _mockPost: string };
    expect(res._mockPost).toBe('/v1/geo-hub/imagery-layers/');
  });

  it('listTerrainSources is unscoped', async () => {
    const res = (await listTerrainSources()) as unknown as Record<string, string>;
    expect(res._mockGet).toBe('/v1/geo-hub/terrain-sources/');
  });

  it('createViewpoint POSTs to /viewpoints/', async () => {
    const res = (await createViewpoint({
      project_id: PROJECT,
      name: 'Top',
      camera_lat: '0',
      camera_lon: '0',
    })) as unknown as { _mockPost: string };
    expect(res._mockPost).toBe('/v1/geo-hub/viewpoints/');
  });

  it('listImageryLayers uses /imagery-layers/', async () => {
    const res = (await listImageryLayers(PROJECT)) as unknown as Record<
      string, string
    >;
    expect(res._mockGet).toBe(
      `/v1/geo-hub/imagery-layers/?project_id=${PROJECT}`,
    );
  });

  it('listViewpoints uses /viewpoints/', async () => {
    const res = (await listViewpoints(PROJECT)) as unknown as Record<string, string>;
    expect(res._mockGet).toBe(`/v1/geo-hub/viewpoints/?project_id=${PROJECT}`);
  });

  it('listOverlays passes kind filter', async () => {
    const res = (await listOverlays(PROJECT, 'flood_zone')) as unknown as Record<
      string, string
    >;
    expect(res._mockGet).toContain('kind=flood_zone');
  });

  it('importGeoJSON POSTs to /overlays/import-geojson/', async () => {
    const res = (await importGeoJSON({
      project_id: PROJECT,
      geojson: { type: 'FeatureCollection', features: [] },
    })) as unknown as { _mockPost: string };
    expect(res._mockPost).toBe('/v1/geo-hub/overlays/import-geojson/');
  });

  it('importKML POSTs to /overlays/import-kml/', async () => {
    const res = (await importKML({
      project_id: PROJECT,
      kml: '<kml/>',
    })) as unknown as { _mockPost: string };
    expect(res._mockPost).toBe('/v1/geo-hub/overlays/import-kml/');
  });

  it('exportGeoJSON GETs /overlays/export-geojson/', async () => {
    const res = (await exportGeoJSON(PROJECT, {
      kind: 'boundary',
    })) as unknown as Record<string, string>;
    expect(res._mockGet).toContain('/v1/geo-hub/overlays/export-geojson/');
    expect(res._mockGet).toContain(`project_id=${PROJECT}`);
    expect(res._mockGet).toContain('kind=boundary');
  });

  it('exportGeoJSON forwards include layers', async () => {
    const res = (await exportGeoJSON(PROJECT, {
      include: ['anchor', 'hse'],
    })) as unknown as Record<string, string>;
    expect(res._mockGet).toContain('/v1/geo-hub/overlays/export-geojson/');
    expect(res._mockGet).toContain('include=anchor%2Chse');
  });
});
