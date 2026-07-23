// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Tests for prefetchModelTiles - the "save this model for offline" path.
 *
 * It must warm the SAME content-addressed cache streamModelTiles reads (so a
 * later open is a pure cache hit), skip tiles already cached, survive individual
 * tile failures without aborting the whole save, and report honest progress. We
 * mock the tile cache and the auth store and drive a fake `fetch`, so these are
 * pure behaviour assertions with no IndexedDB and no network.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { TileInfo, TileManifest } from './tileTypes';

// Proven repo idiom (see features/rfi/__tests__/api.test.ts): declare the mock
// fns first, reference them from the vi.mock factory.
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

import { prefetchModelTiles } from './tileStreamer';

function tile(id: string, hash: string): TileInfo {
  return {
    id,
    hash,
    bbox: [0, 0, 0, 1, 1, 1],
    center: [0.5, 0.5, 0.5],
    radius: 1,
    node_count: 1,
    byte_size: 8,
    nodes: [`node_${id}`],
  };
}

function manifest(tiles: TileInfo[]): TileManifest {
  return {
    tiler_version: 'test',
    up_axis: 'Y',
    bounds: [0, 0, 0, 1, 1, 1],
    mesh_count: tiles.length,
    tile_count: tiles.length,
    total_bytes: tiles.length * 8,
    tiles,
  };
}

interface FetchScript {
  manifest: TileManifest | null;
  /** Tile hashes whose download should fail (HTTP 500). */
  failHashes?: string[];
}

/** Records which tile hashes hit the network. */
const fetchedHashes: string[] = [];

function installFetch(script: FetchScript): void {
  const fail = new Set(script.failHashes ?? []);
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
    const url = String(input);
    if (url.includes('/manifest/')) {
      if (script.manifest === null) {
        return { ok: false, status: 204, json: async () => ({}) } as unknown as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => script.manifest,
      } as unknown as Response;
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
    return {
      ok: true,
      status: 200,
      arrayBuffer: async () => new ArrayBuffer(8),
    } as unknown as Response;
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

describe('prefetchModelTiles', () => {
  it('returns null when the model has no tileset', async () => {
    installFetch({ manifest: null });
    const result = await prefetchModelTiles('m1');
    expect(result).toBeNull();
    // No tiles were fetched (only the manifest probe, which 204'd).
    expect(fetchedHashes).toEqual([]);
  });

  it('downloads and caches every tile, reporting all ok', async () => {
    installFetch({ manifest: manifest([tile('t1', 'a'), tile('t2', 'b'), tile('t3', 'c')]) });
    const result = await prefetchModelTiles('m1');
    expect(result).toEqual({ total: 3, ok: 3, failed: 0 });
    expect(new Set(fetchedHashes)).toEqual(new Set(['a', 'b', 'c']));
    // Each downloaded tile was written to the same cache streaming reads.
    expect(putCachedTile).toHaveBeenCalledTimes(3);
    expect(putCachedTile).toHaveBeenCalledWith('m1:a', expect.any(ArrayBuffer));
  });

  it('skips tiles already in the cache (no network hit) but still counts them ok', async () => {
    // 'b' is already saved; only 'a' and 'c' should touch the network.
    getCachedTile.mockImplementation(async (key: string) =>
      key === 'm1:b' ? new ArrayBuffer(8) : null,
    );
    installFetch({ manifest: manifest([tile('t1', 'a'), tile('t2', 'b'), tile('t3', 'c')]) });
    const result = await prefetchModelTiles('m1');
    expect(result).toEqual({ total: 3, ok: 3, failed: 0 });
    expect(new Set(fetchedHashes)).toEqual(new Set(['a', 'c']));
    expect(fetchedHashes).not.toContain('b');
    // A cache hit is not re-written.
    expect(putCachedTile).toHaveBeenCalledTimes(2);
  });

  it('counts a failing tile without aborting the rest', async () => {
    installFetch({
      manifest: manifest([tile('t1', 'a'), tile('t2', 'b'), tile('t3', 'c')]),
      failHashes: ['b'],
    });
    const result = await prefetchModelTiles('m1');
    expect(result).toEqual({ total: 3, ok: 2, failed: 1 });
    // The good tiles were still cached even though one failed.
    expect(putCachedTile).toHaveBeenCalledTimes(2);
  });

  it('reports monotonic progress that ends at total', async () => {
    installFetch({ manifest: manifest([tile('t1', 'a'), tile('t2', 'b')]) });
    const seen: number[] = [];
    let last = { done: 0, total: 0, ok: 0, failed: 0 };
    await prefetchModelTiles('m1', {
      fetchConcurrency: 1,
      onProgress: (p) => {
        seen.push(p.done);
        last = p;
      },
    });
    expect(seen).toEqual([1, 2]);
    expect(last).toEqual({ done: 2, total: 2, ok: 2, failed: 0 });
  });

  it('does nothing per tile when the signal is already aborted', async () => {
    installFetch({ manifest: manifest([tile('t1', 'a'), tile('t2', 'b')]) });
    const controller = new AbortController();
    controller.abort();
    const result = await prefetchModelTiles('m1', { signal: controller.signal });
    // The tileset was discovered, but no tile was downloaded or counted.
    expect(result).toEqual({ total: 2, ok: 0, failed: 0 });
    expect(fetchedHashes).toEqual([]);
    expect(putCachedTile).not.toHaveBeenCalled();
  });

  it('honours a custom download concurrency', async () => {
    installFetch({ manifest: manifest([tile('t1', 'a'), tile('t2', 'b'), tile('t3', 'c')]) });
    const result = await prefetchModelTiles('m1', { fetchConcurrency: 2 });
    expect(result).toEqual({ total: 3, ok: 3, failed: 0 });
  });
});
