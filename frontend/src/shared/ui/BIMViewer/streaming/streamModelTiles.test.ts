// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Tests for the progressive streaming contract of streamModelTiles.
 *
 * The loader must: reveal each tile the moment it parses (onTileParsed once per
 * parsed tile, all handed the same accumulating group), stream the tiles that
 * carry the most geometry first, drive onProgress to 1, skip a tile that fails
 * to download without aborting the rest, and return null when there is no
 * tileset. We mock the GLB parser, the tile cache, the auth store and fetch, so
 * this exercises the pipeline with no WebGL and no network.
 */

import * as THREE from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { TileInfo, TileManifest } from './tileTypes';

// Each parse yields a scene with exactly one child, so the merged group's child
// count equals the number of tiles that parsed.
vi.mock('three/addons/loaders/GLTFLoader.js', async () => {
  const three = await vi.importActual<typeof import('three')>('three');
  return {
    GLTFLoader: class {
      parse(
        _buffer: ArrayBuffer,
        _path: string,
        onLoad: (gltf: { scene: THREE.Object3D }) => void,
      ): void {
        const scene = new three.Group();
        scene.add(new three.Object3D());
        onLoad({ scene });
      }
    },
  };
});

const getCachedTile = vi.fn(async (_key: string): Promise<ArrayBuffer | null> => null);
const putCachedTile = vi.fn(async (_key: string, _buf: ArrayBuffer): Promise<void> => undefined);

vi.mock('./tileCache', () => ({
  getCachedTile: (key: string) => getCachedTile(key),
  putCachedTile: (key: string, buf: ArrayBuffer) => putCachedTile(key, buf),
  tileCacheKey: (modelId: string, hash: string) => `${modelId}:${hash}`,
}));

vi.mock('@/stores/useAuthStore', () => ({
  useAuthStore: { getState: () => ({ accessToken: 'test-token' }) },
}));

import { streamModelTiles } from './tileStreamer';

const GLB_MAGIC = 0x46546c67;

/** A minimal buffer that passes parseTile's GLB magic check. */
function glbBuffer(): ArrayBuffer {
  const buffer = new ArrayBuffer(16);
  new Uint32Array(buffer, 0, 1)[0] = GLB_MAGIC;
  return buffer;
}

function tile(id: string, overrides: Partial<TileInfo> = {}): TileInfo {
  return {
    id,
    hash: id,
    bbox: [0, 0, 0, 1, 1, 1],
    center: [0, 0, 0],
    radius: 1,
    node_count: 1,
    byte_size: 100,
    nodes: [],
    ...overrides,
  };
}

function manifest(tiles: TileInfo[]): TileManifest {
  return {
    tiler_version: 'test',
    up_axis: 'Y',
    bounds: [0, 0, 0, 1, 1, 1],
    mesh_count: tiles.length,
    tile_count: tiles.length,
    total_bytes: tiles.length * 100,
    tiles,
  };
}

const fetchedHashes: string[] = [];

function installFetch(m: TileManifest | null, failHashes: string[] = []): void {
  const fail = new Set(failHashes);
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
    const url = String(input);
    if (url.includes('/manifest/')) {
      if (m === null)
        return { ok: false, status: 204, json: async () => ({}) } as unknown as Response;
      return { ok: true, status: 200, json: async () => m } as unknown as Response;
    }
    const match = url.match(/\/tiles\/([^/]+)\//);
    const hash = match?.[1] ? decodeURIComponent(match[1]) : '';
    fetchedHashes.push(hash);
    if (fail.has(hash)) {
      return {
        ok: false,
        status: 500,
        arrayBuffer: async () => new ArrayBuffer(0),
      } as unknown as Response;
    }
    return { ok: true, status: 200, arrayBuffer: async () => glbBuffer() } as unknown as Response;
  }) as unknown as typeof fetch;
}

beforeEach(() => {
  getCachedTile.mockReset().mockResolvedValue(null);
  putCachedTile.mockReset().mockResolvedValue(undefined);
  fetchedHashes.length = 0;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('streamModelTiles progressive contract', () => {
  it('returns null when the model has no tileset', async () => {
    installFetch(null);
    expect(await streamModelTiles('m1')).toBeNull();
  });

  it('reveals every tile via onTileParsed and drives progress to 1', async () => {
    installFetch(manifest([tile('a'), tile('b'), tile('c')]));
    const reveals: number[] = [];
    let lastProgress = 0;
    const result = await streamModelTiles('m1', {
      onTileParsed: (group) => reveals.push(group.children.length),
      onProgress: (f) => {
        lastProgress = f;
      },
    });
    expect(result).not.toBeNull();
    expect(result?.tileCount).toBe(3);
    expect(result?.meshCount).toBe(3);
    // onTileParsed fires once per parsed tile, each time with the accumulating
    // group, so the child count climbs 1,2,3.
    expect(reveals).toEqual([1, 2, 3]);
    expect(lastProgress).toBe(1);
    // The returned group is the very one handed to onTileParsed.
    expect(result?.group).toBeInstanceOf(THREE.Group);
  });

  it('streams the highest-geometry tiles first', async () => {
    installFetch(
      manifest([
        tile('small', { node_count: 2 }),
        tile('huge', { node_count: 900 }),
        tile('medium', { node_count: 40 }),
      ]),
    );
    // Concurrency 1 makes the fetch order deterministic = the priority order.
    await streamModelTiles('m1', { fetchConcurrency: 1 });
    expect(fetchedHashes).toEqual(['huge', 'medium', 'small']);
  });

  it('streams viewport-first when a camera pose is provided', async () => {
    installFetch(
      manifest([
        // 'far' carries the most geometry, so mass order would fetch it first;
        // the camera pose must override that and fetch the nearest tile first.
        tile('far', { center: [0, 0, 10], node_count: 100 }),
        tile('near', { center: [0, 0, 1], node_count: 1 }),
        tile('mid', { center: [0, 0, 3], node_count: 50 }),
      ]),
    );
    await streamModelTiles('m1', {
      fetchConcurrency: 1,
      getCameraPose: () => ({ position: [50, 50, 50], target: [0, 0, 0] }),
    });
    expect(fetchedHashes).toEqual(['near', 'mid', 'far']);
  });

  it('keeps geometry-mass order when the camera pose probe returns null', async () => {
    installFetch(manifest([tile('small', { node_count: 2 }), tile('huge', { node_count: 900 })]));
    await streamModelTiles('m1', { fetchConcurrency: 1, getCameraPose: () => null });
    expect(fetchedHashes).toEqual(['huge', 'small']);
  });

  it('skips a tile that fails to download and keeps the rest', async () => {
    installFetch(manifest([tile('a'), tile('b'), tile('c')]), ['b']);
    const result = await streamModelTiles('m1');
    // Two good tiles parsed; the failed one is skipped, not fatal.
    expect(result?.tileCount).toBe(2);
    expect(result?.meshCount).toBe(2);
  });

  it('returns null when nothing parses (all tiles fail to download)', async () => {
    installFetch(manifest([tile('a'), tile('b')]), ['a', 'b']);
    expect(await streamModelTiles('m1')).toBeNull();
  });
});
