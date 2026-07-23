// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Streaming tile ordering.
 *
 * The streamer downloads and reveals tiles in whatever order the manifest lists
 * them, which is spatial-octree order, not importance order. On the initial load
 * there is no meaningful camera yet (the view fits to the model only after it
 * arrives), so we cannot sort by what the user is looking at. Instead we order by
 * how much of the building each tile carries: the tiles with the most geometry
 * first, so the bulk of the structure appears while the small trailing tiles are
 * still coming in. Within an equal-mass tie we go ground-up, so a building rises
 * from its base rather than filling in at random.
 *
 * Pure and deterministic (no camera, no THREE, no DOM): input tiles in, a new
 * ordered array out. The manifest already carries the per-tile node_count /
 * byte_size / center the backend tiler bakes, so this reads for free.
 */

import type { TileInfo } from './tileTypes';

/** Finite number or a fallback - guards against malformed manifest entries. */
function num(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

/**
 * Vertical position of a tile in tile-local coordinates. Tiles are baked in the
 * source's Z-up frame (the viewer rotates -90 deg X on display), so the vertical
 * axis here is Z = center[2]. Lower means closer to the ground.
 */
function tileHeight(tile: TileInfo): number {
  return Array.isArray(tile.center) ? num(tile.center[2]) : 0;
}

/**
 * Return a NEW array of the tiles ordered for streaming: most geometry first,
 * then largest payload, then ground-up, with the original manifest order as the
 * final deterministic tie-break. Does not mutate the input.
 */
export function orderTilesForStreaming(tiles: TileInfo[]): TileInfo[] {
  return tiles
    .map((tile, index) => ({ tile, index }))
    .sort((a, b) => {
      // 1. More meshes = more of the building = show first.
      const nodeDelta = num(b.tile.node_count) - num(a.tile.node_count);
      if (nodeDelta !== 0) return nodeDelta;
      // 2. Bigger payload next (a proxy for geometry volume when node_count ties).
      const sizeDelta = num(b.tile.byte_size) - num(a.tile.byte_size);
      if (sizeDelta !== 0) return sizeDelta;
      // 3. Ground-up so the structure rises from its base.
      const heightDelta = tileHeight(a.tile) - tileHeight(b.tile);
      if (heightDelta !== 0) return heightDelta;
      // 4. Stable, deterministic fallback: keep the original manifest order.
      return a.index - b.index;
    })
    .map((entry) => entry.tile);
}

/** A camera pose in viewer-world space, enough to rank tiles by what the
 *  user is looking at. Positions are in metres in the viewer's Y-up frame. */
export interface CameraPose {
  /** Camera eye position [x, y, z]. */
  position: [number, number, number];
  /** Look-at / orbit target [x, y, z]. Optional; when absent only the eye
   *  distance is used. */
  target?: [number, number, number];
}

/**
 * Tile bounding-sphere centre expressed in the viewer's world frame.
 *
 * Tiles are baked in the source's Z-up frame and the viewer displays them
 * under a single -90 deg rotation about X (no translation, no scale - see the
 * streaming reveal in ElementManager). That rotation maps a source point
 * (x, y, z) to (x, z, -y), so a tile whose source centre is `center` sits at
 * [x, z, -y] on screen. We rank against that so "near the camera" means near
 * where the geometry actually appears, not where it was authored.
 *
 * Pure and allocation-light; guards malformed centres to the origin.
 */
export function tileCenterInViewerSpace(tile: TileInfo): [number, number, number] {
  const c = tile.center;
  if (!Array.isArray(c)) return [0, 0, 0];
  const x = num(c[0]);
  const y = num(c[1]);
  const z = num(c[2]);
  return [x, z, -y];
}

/** Squared distance from a tile (in viewer space) to the more relevant of the
 *  camera target or eye. Squared to avoid a sqrt in the hot ranking loop. */
function tileCameraDistanceSq(tile: TileInfo, pose: CameraPose): number {
  const [tx, ty, tz] = tileCenterInViewerSpace(tile);
  const ref = pose.target ?? pose.position;
  const dx = tx - num(ref[0]);
  const dy = ty - num(ref[1]);
  const dz = tz - num(ref[2]);
  return dx * dx + dy * dy + dz * dz;
}

/**
 * Return a NEW array of the tiles ordered by what the camera is looking at:
 * nearest to the camera target (or eye) first, so the region on screen fills
 * in before the far side of the building. This is the "viewport-priority"
 * order used once the camera is meaningfully placed - most importantly when a
 * deep-link (clash review, element focus) has already pointed the camera at a
 * specific spot while the geometry is still streaming in.
 *
 * Ties (equidistant tiles) fall back to the geometry-mass order so the meatier
 * tile of two at the same distance still wins, then to manifest order for full
 * determinism. Pure: no THREE, no camera object, no mutation of the input.
 */
export function orderTilesByViewport(tiles: TileInfo[], pose: CameraPose): TileInfo[] {
  return tiles
    .map((tile, index) => ({ tile, index, dist: tileCameraDistanceSq(tile, pose) }))
    .sort((a, b) => {
      // 1. Nearer the camera = show first (the whole point of viewport order).
      if (a.dist !== b.dist) return a.dist - b.dist;
      // 2. Equidistant: prefer the tile carrying more of the building.
      const nodeDelta = num(b.tile.node_count) - num(a.tile.node_count);
      if (nodeDelta !== 0) return nodeDelta;
      const sizeDelta = num(b.tile.byte_size) - num(a.tile.byte_size);
      if (sizeDelta !== 0) return sizeDelta;
      // 3. Stable, deterministic fallback: original manifest order.
      return a.index - b.index;
    })
    .map((entry) => entry.tile);
}
