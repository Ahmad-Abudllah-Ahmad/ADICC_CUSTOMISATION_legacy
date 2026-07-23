#!/usr/bin/env node
/**
 * build-pwa-icons.mjs — optionally rasterize PWA SVG icons to PNG.
 *
 * The PWA manifest in vite.config.ts references SVG icons under
 * /pwa/icon-*.svg. Modern browsers (Chrome 88+, Edge 88+, Firefox,
 * Safari 16.4+ in standalone PWAs) accept SVG icons in a manifest
 * directly, so the SVGs alone are enough for an installable PWA.
 *
 * This script is a *defensive* extra step for environments where
 * older clients want PNGs, OR for the OS install dialog on iOS /
 * Windows store where PNG fingerprints are still preferred. It
 * requires the optional `sharp` dependency; if `sharp` is not
 * installed, the script exits 0 with an explanatory log line so it
 * never breaks CI.
 *
 * Run manually:
 *   node frontend/scripts/build-pwa-icons.mjs
 *
 * Output: frontend/public/pwa/icon-{192,256,384,512}.png +
 *         frontend/public/pwa/icon-maskable-512.png
 */
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const pwaDir = path.resolve(__dirname, '..', 'public', 'pwa');

const SIZES = [192, 256, 384, 512];

async function loadSharp() {
  try {
    const mod = await import('sharp');
    return mod.default ?? mod;
  } catch {
    return null;
  }
}

async function main() {
  const sharp = await loadSharp();
  if (!sharp) {
    // eslint-disable-next-line no-console
    console.log(
      '[pwa-icons] `sharp` is not installed — skipping PNG rasterization. ' +
        'SVG icons in /public/pwa/ are sufficient for the manifest.',
    );
    process.exit(0);
  }

  for (const size of SIZES) {
    const svgPath = path.join(pwaDir, `icon-${size}.svg`);
    const pngPath = path.join(pwaDir, `icon-${size}.png`);
    const svg = await fs.readFile(svgPath);
    await sharp(svg).resize(size, size).png().toFile(pngPath);
    // eslint-disable-next-line no-console
    console.log(`[pwa-icons] wrote ${pngPath}`);
  }

  // Maskable
  const maskSvg = await fs.readFile(path.join(pwaDir, 'icon-maskable-512.svg'));
  const maskPng = path.join(pwaDir, 'icon-maskable-512.png');
  await sharp(maskSvg).resize(512, 512).png().toFile(maskPng);
  // eslint-disable-next-line no-console
  console.log(`[pwa-icons] wrote ${maskPng}`);
}

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error('[pwa-icons] failed:', err);
  process.exit(1);
});
