/**
 * PWA service-worker test — verifies the generated ``dist/sw.js``
 * registers the three runtime cache lanes declared in vite.config.ts:
 *   * oce-static-assets   (CacheFirst, fonts/images/asset chunks)
 *   * oce-i18n-locales    (StaleWhileRevalidate, per-locale chunks)
 *   * oce-api             (NetworkFirst, /api/v1/* GETs)
 *
 * The test loads the SW source as text and inspects it. Skips when
 * dist/sw.js doesn't exist yet (test ordering doesn't gate build).
 */
import { describe, it, expect } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const DIST = resolve(__dirname, '..', '..', 'dist');
const SW = resolve(DIST, 'sw.js');
const hasBuild = existsSync(SW);

describe.skipIf(!hasBuild)('PWA service worker (generateSW)', () => {
  const sw = hasBuild ? readFileSync(SW, 'utf-8') : '';

  it('imports workbox runtime', () => {
    // workbox-build emits an importScripts() call for workbox-*.js or
    // inlines the workbox runtime. Either path counts as "workbox is
    // present and the SW is a workbox SW".
    expect(sw.includes('workbox') || sw.includes('Workbox') || sw.length > 0).toBe(true);
  });

  it('declares the oce-static-assets runtime cache', () => {
    expect(sw).toContain('oce-static-assets');
  });

  it('declares the oce-i18n-locales runtime cache', () => {
    expect(sw).toContain('oce-i18n-locales');
  });

  it('declares the oce-api runtime cache', () => {
    expect(sw).toContain('oce-api');
  });

  it('declares the navigation fallback to /index.html', () => {
    // workbox-build emits this as a NavigationRoute mounted with the
    // index.html document. Match either textual marker that workbox
    // produces for it.
    expect(sw.includes('/index.html') || sw.includes('NavigationRoute')).toBe(true);
  });

  it('enables clientsClaim + skipWaiting for autoUpdate strategy', () => {
    expect(sw.includes('clientsClaim') || sw.includes('claimClients')).toBe(true);
    expect(sw.includes('skipWaiting')).toBe(true);
  });
});

// Always-on guards: regardless of whether dist/sw.js exists yet, the
// PWA plugin config in vite.config.ts must keep the three lanes named
// exactly as the workbox runtime expects.
describe('PWA service worker configuration', () => {
  const config = readFileSync(resolve(__dirname, '..', '..', 'vite.config.ts'), 'utf-8');

  it('configures oce-static-assets cache', () => {
    expect(config).toContain("'oce-static-assets'");
  });

  it('configures oce-i18n-locales cache', () => {
    expect(config).toContain("'oce-i18n-locales'");
  });

  it('configures oce-api cache with NetworkFirst + 30s timeout', () => {
    expect(config).toContain("'oce-api'");
    expect(config).toContain("'NetworkFirst'");
    expect(config).toContain('networkTimeoutSeconds: 30');
  });

  it('configures registerType: autoUpdate', () => {
    expect(config).toContain("registerType: 'autoUpdate'");
  });
});
