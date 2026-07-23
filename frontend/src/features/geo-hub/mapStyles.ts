// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Basemap styles for the lightweight 2D Geo Hub map (MapLibre GL).
 *
 * The Geo Hub ships two rendering engines:
 *
 *   * the 3D globe (Cesium) - rich, heavy (~3 MB runtime), best for
 *     terrain + 3D tilesets;
 *   * this 2D map (MapLibre GL) - light, instant, "like paper", best for
 *     quickly placing projects and drawings on a clear, readable map.
 *
 * Every style here is fully open-source and self-hostable:
 *
 *   * ``streets`` / ``minimal`` pull raster tiles from our OWN same-origin
 *     backend proxy (see ``shared/ui/ProjectMap/basemap``), which fetches
 *     the OpenStreetMap-derived CARTO basemap server-side. No external CDN
 *     at runtime, no API key, works behind ad/privacy blockers.
 *   * ``paper`` / ``blueprint`` use NO tiles at all - just a flat drawn
 *     background. They render fully offline (air-gapped / no internet) and
 *     give the clean "drawing on paper" canvas for placing projects and
 *     georeferenced drawings. Nothing leaves the browser.
 *
 * Switching a basemap is a single MapLibre ``setStyle`` (or a React
 * ``mapStyle`` prop swap) - instant, no reload.
 */
import type { StyleSpecification } from 'maplibre-gl';

import { PROXY_TILE_URL, TILE_ATTRIBUTION } from '@/shared/ui/ProjectMap/basemap';

/** Identifier for each selectable basemap. */
export type BasemapId = 'streets' | 'minimal' | 'paper' | 'blueprint';

/** Default basemap for a fresh 2D session - the readable full-colour map. */
export const DEFAULT_BASEMAP: BasemapId = 'streets';

/** localStorage key persisting the user's basemap choice across reloads. */
export const BASEMAP_LS_KEY = 'geoHub.basemap';

/**
 * Lucide icon name (resolved by the picker) + i18n metadata for each
 * basemap. Kept as data so the picker stays a thin presentational list.
 */
export interface BasemapMeta {
  id: BasemapId;
  /** Lucide icon name rendered by the picker. */
  icon: 'Map' | 'Layers' | 'FileText' | 'Grid3x3';
  labelKey: string;
  labelDefault: string;
  descKey: string;
  descDefault: string;
  /** ``true`` for the tile-free, fully-offline drawn backgrounds. */
  offline: boolean;
  /** Whether pins/labels should render in a light treatment (dark bg). */
  dark: boolean;
}

export const BASEMAPS = [
  {
    id: 'streets',
    icon: 'Map',
    labelKey: 'geo.basemap.streets',
    labelDefault: 'Streets',
    descKey: 'geo.basemap.streets_hint',
    descDefault: 'Full-colour street map (OpenStreetMap / CARTO).',
    offline: false,
    dark: false,
  },
  {
    id: 'minimal',
    icon: 'Layers',
    labelKey: 'geo.basemap.minimal',
    labelDefault: 'Minimal',
    descKey: 'geo.basemap.minimal_hint',
    descDefault: 'Light, desaturated map - less clutter, easy to read.',
    offline: false,
    dark: false,
  },
  {
    id: 'paper',
    icon: 'FileText',
    labelKey: 'geo.basemap.paper',
    labelDefault: 'Paper',
    descKey: 'geo.basemap.paper_hint',
    descDefault: 'Plain paper canvas - no tiles, works fully offline.',
    offline: true,
    dark: false,
  },
  {
    id: 'blueprint',
    icon: 'Grid3x3',
    labelKey: 'geo.basemap.blueprint',
    labelDefault: 'Blueprint',
    descKey: 'geo.basemap.blueprint_hint',
    descDefault: 'Dark drafting canvas - no tiles, works fully offline.',
    offline: true,
    dark: true,
  },
] as const satisfies readonly BasemapMeta[];

export function basemapMeta(id: BasemapId): BasemapMeta {
  return BASEMAPS.find((b) => b.id === id) ?? BASEMAPS[0];
}

/** Read the persisted basemap choice (SSR / quota safe). */
export function readBasemap(): BasemapId {
  if (typeof window === 'undefined') return DEFAULT_BASEMAP;
  try {
    const v = window.localStorage.getItem(BASEMAP_LS_KEY);
    if (v === 'streets' || v === 'minimal' || v === 'paper' || v === 'blueprint') {
      return v;
    }
  } catch {
    /* localStorage disabled / quota - fall through to default */
  }
  return DEFAULT_BASEMAP;
}

// ── Style builders ───────────────────────────────────────────────────────

/**
 * Raster basemap from the same-origin proxy. ``minimal`` desaturates and
 * fades the tiles over a light background so the map reads as a clean,
 * low-clutter "minimal" surface; ``streets`` paints them at full colour.
 */
function rasterStyle(variant: 'streets' | 'minimal'): StyleSpecification {
  const minimal = variant === 'minimal';
  return {
    version: 8,
    sources: {
      'oe-basemap': {
        type: 'raster',
        tiles: [PROXY_TILE_URL],
        tileSize: 256,
        maxzoom: 20,
        attribution: TILE_ATTRIBUTION,
      },
    },
    layers: [
      // Background shows through before tiles load (and through the faded
      // ``minimal`` tiles), so it sets the overall tone of the map.
      {
        id: 'oe-bg',
        type: 'background',
        paint: { 'background-color': minimal ? '#f8fafc' : '#e8eef3' },
      },
      {
        id: 'oe-basemap',
        type: 'raster',
        source: 'oe-basemap',
        paint: minimal
          ? {
              // Grayscale + reduced contrast, and let the light background
              // show through for a faded, paper-like minimal look.
              'raster-saturation': -1,
              'raster-contrast': -0.05,
              'raster-opacity': 0.55,
            }
          : {},
      },
    ],
  };
}

/**
 * Tile-free background-only style. Renders fully offline - no network
 * request ever leaves the browser. Projects and georeferenced drawings
 * are painted on top by the viewer as markers and image layers, giving a
 * clean "drawing on paper" canvas.
 */
function flatStyle(background: string): StyleSpecification {
  return {
    version: 8,
    sources: {},
    layers: [
      {
        id: 'oe-bg',
        type: 'background',
        paint: { 'background-color': background },
      },
    ],
  };
}

/** Background colour for the tile-free styles - reused by the viewer so
 *  the map container matches the canvas before MapLibre paints. */
export const BASEMAP_BACKDROP: Record<BasemapId, string> = {
  streets: '#e8eef3',
  minimal: '#f8fafc',
  paper: '#f4efe2',
  blueprint: '#0e2a47',
};

/**
 * Build the MapLibre style for a basemap id. Cheap + pure, so callers can
 * call it inline in render and memoise on ``id`` alone.
 */
export function buildBasemapStyle(id: BasemapId): StyleSpecification {
  switch (id) {
    case 'minimal':
      return rasterStyle('minimal');
    case 'paper':
      return flatStyle(BASEMAP_BACKDROP.paper);
    case 'blueprint':
      return flatStyle(BASEMAP_BACKDROP.blueprint);
    case 'streets':
    default:
      return rasterStyle('streets');
  }
}
