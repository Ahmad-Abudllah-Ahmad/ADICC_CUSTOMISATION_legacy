// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Shared basemap configuration.
 *
 * Every map in the app - the Cesium globe, the MapLibre 2D maps, and the
 * static card thumbnails - pulls its raster tiles from our own backend proxy
 * at ``/api/v1/geo-hub/tiles/{z}/{x}/{y}.png`` instead of straight from a
 * public CDN. Browser ad and privacy blockers routinely block the public
 * tile hosts (``basemaps.cartocdn.com``, the OpenStreetMap servers), which
 * leaves maps showing a blank blue square. A same-origin ``/api`` request is
 * never blocked, so the proxy fetches the CARTO "Voyager" basemap server-side
 * with a proper User-Agent and an in-process cache. One tile source for the
 * whole app, no external runtime dependency, works in any browser.
 */
import type { StyleSpecification } from 'maplibre-gl';

/** XYZ template served by the backend tile proxy (same origin). */
export const PROXY_TILE_URL = '/api/v1/geo-hub/tiles/{z}/{x}/{y}.png';

/** Base path (without ``/{z}/{x}/{y}.png``) for static single-tile thumbnails. */
export const PROXY_TILE_BASE = '/api/v1/geo-hub/tiles';

export const TILE_ATTRIBUTION = '© OpenStreetMap contributors © CARTO';

/**
 * Minimal MapLibre raster style backed by the proxy. No glyphs or sprites
 * are needed: every label and marker in our maps is a React overlay, not a
 * style symbol layer, so a single raster source + raster layer is enough.
 */
export const RASTER_BASEMAP_STYLE: StyleSpecification = {
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
  layers: [{ id: 'oe-basemap', type: 'raster', source: 'oe-basemap' }],
};
