/**
 * PWA manifest test — verifies the generated ``dist/manifest.webmanifest``
 * has the fields required by an installable PWA and that they match
 * the values we declared in ``vite.config.ts``.
 *
 * This test runs against the BUILD OUTPUT.  If ``frontend/dist/`` does
 * not exist yet (e.g. CI step running tests before build) the test
 * skips itself instead of failing — the manifest is a build artefact
 * and we don't want PWA tests to gate the regular unit-test loop.
 */
import { describe, it, expect } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const DIST = resolve(__dirname, '..', '..', 'dist');
const MANIFEST = resolve(DIST, 'manifest.webmanifest');

const hasBuild = existsSync(MANIFEST);

describe.skipIf(!hasBuild)('PWA manifest', () => {
  // Build output exists — fully assert.
  const raw = hasBuild ? readFileSync(MANIFEST, 'utf-8') : '{}';
  const manifest = JSON.parse(raw) as Record<string, unknown>;

  it('has the required identity fields', () => {
    expect(manifest.name).toBe('OpenConstructionERP');
    expect(manifest.short_name).toBe('OCERP');
    expect(typeof manifest.description).toBe('string');
  });

  it('sets the OCE theme palette', () => {
    expect(manifest.theme_color).toBe('#0284c7');
    expect(manifest.background_color).toBe('#f7fbff');
  });

  it('declares display=standalone and the root scope', () => {
    expect(manifest.display).toBe('standalone');
    expect(manifest.start_url).toBe('/');
    expect(manifest.scope).toBe('/');
  });

  it('ships icons in 192/256/384/512 + a maskable variant', () => {
    const icons = manifest.icons as Array<{ src: string; sizes: string; purpose?: string }>;
    expect(Array.isArray(icons)).toBe(true);

    const sizes = icons.map((i) => i.sizes);
    expect(sizes).toContain('192x192');
    expect(sizes).toContain('256x256');
    expect(sizes).toContain('384x384');
    expect(sizes).toContain('512x512');

    const maskable = icons.find((i) => (i.purpose ?? '').includes('maskable'));
    expect(maskable, 'manifest must include a maskable icon for adaptive launchers').toBeTruthy();

    // Every src should resolve under /pwa/
    for (const icon of icons) {
      expect(icon.src.startsWith('/pwa/')).toBe(true);
    }
  });
});

// Always-on assertion: even without a build, fail loudly if someone
// edits vite.config.ts to drop the PWA plugin — the test file itself
// would still pass if every check were skipConditioned.  Verify the
// vite config string contains the manifest name.
describe('PWA plugin configuration', () => {
  it('vite.config.ts still wires VitePWA with the OCERP manifest', () => {
    const config = readFileSync(resolve(__dirname, '..', '..', 'vite.config.ts'), 'utf-8');
    expect(config).toContain("VitePWA");
    expect(config).toContain("'OpenConstructionERP'");
    expect(config).toContain("'OCERP'");
    expect(config).toContain("'#0284c7'");
  });
});
