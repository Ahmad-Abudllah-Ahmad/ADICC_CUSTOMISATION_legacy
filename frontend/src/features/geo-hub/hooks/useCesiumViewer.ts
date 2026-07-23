// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Cesium viewer lifecycle hook.
 *
 * Wraps Cesium's ``Viewer`` constructor + ``destroy()`` cleanup so the
 * component code stays focused on event wiring + UI. The hook is
 * intentionally framework-light: a single ``useEffect`` body, no
 * external deps beyond React.
 */

import { useEffect, useRef, useState } from 'react';

import type { MapConfig } from '../types';

type ViewerHandle = {
  destroy: () => void;
};

type CesiumLike = {
  Viewer: new (
    container: HTMLElement,
    options?: Record<string, unknown>,
  ) => ViewerHandle;
  EllipsoidTerrainProvider: new () => unknown;
  UrlTemplateImageryProvider: new (options: Record<string, unknown>) => unknown;
  ImageryLayer: new (provider: unknown) => unknown;
};

/**
 * Hook return:
 *
 * * ``ref`` — pass to the container ``<div ref={ref} />``.
 * * ``status`` — `'pending'` while Cesium loads, `'loaded'` once the
 *   viewer is constructed, `'absent'` when CesiumJS is not installed.
 */
export function useCesiumViewer(_mapConfig?: MapConfig) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<'pending' | 'loaded' | 'absent'>(
    'pending',
  );

  useEffect(() => {
    let disposed = false;
    let viewer: ViewerHandle | null = null;

    (async () => {
      let cesium: CesiumLike | null = null;
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        cesium = (await import('cesium')) as any;
      } catch {
        cesium = null;
      }
      if (disposed) return;
      if (!cesium || !ref.current) {
        setStatus(cesium ? 'pending' : 'absent');
        return;
      }
      try {
        viewer = new cesium.Viewer(ref.current, {
          terrainProvider: new cesium.EllipsoidTerrainProvider(),
          // Basemap tiles come from our own backend proxy, not a public CDN
          // directly. Cesium >= 1.107 otherwise falls back to Ion-backed Bing
          // Maps, which silently 401s without a token. We must not hit the raw
          // OpenStreetMap servers (their policy forbids app use and returns an
          // "Access blocked" tile), and a direct CDN such as CARTO is routinely
          // blocked by browser ad/privacy blockers. The same-origin proxy
          // fetches CARTO server-side with a proper User-Agent and a cache, so
          // the globe works in any browser with no vendor lock-in.
          baseLayer: new cesium.ImageryLayer(
            new cesium.UrlTemplateImageryProvider({
              url: '/api/v1/geo-hub/tiles/{z}/{x}/{y}.png',
              credit: '© OpenStreetMap contributors © CARTO',
              maximumLevel: 20,
            }),
          ),
          baseLayerPicker: false,
        });
        setStatus('loaded');
      } catch {
        setStatus('absent');
      }
    })();

    return () => {
      disposed = true;
      if (viewer) {
        try {
          viewer.destroy();
        } catch {
          /* viewer already gone — ignore */
        }
      }
    };
  }, []);

  return { ref, status };
}
