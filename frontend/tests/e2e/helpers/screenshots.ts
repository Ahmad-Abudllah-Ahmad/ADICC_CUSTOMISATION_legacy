/**
 * screenshots.ts — module-routed screenshot capture (stand-alone helper).
 *
 * This is the lower-level twin of the `captureScreen` fixture in
 * fixtures/screenshot.fixture.ts — useful when you have a Page but no
 * TestInfo (e.g. inside a beforeAll). For most specs, prefer the fixture.
 *
 * Naming: `qa-screenshots/<module>/<module>-<name>-<NN>.png`
 *
 *   await captureScreen(page, 'boq', 'login-page-empty');
 *   // → qa-screenshots/boq/boq-login-page-empty-01.png
 */
import { type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const SCREENSHOT_ROOT = path.resolve(process.cwd(), 'qa-screenshots');

// Per-module auto-increment counters (module-keyed, process-local).
const counters = new Map<string, number>();

function slugify(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64);
}

export async function captureScreen(
  page: Page,
  module: string,
  name: string,
  opts: { fullPage?: boolean } = {},
): Promise<string> {
  const mod = slugify(module);
  const slug = slugify(name);
  const next = (counters.get(mod) ?? 0) + 1;
  counters.set(mod, next);
  const num = String(next).padStart(2, '0');
  const dir = path.join(SCREENSHOT_ROOT, mod);
  fs.mkdirSync(dir, { recursive: true });
  const full = path.join(dir, `${mod}-${slug}-${num}.png`);
  await page.screenshot({ path: full, fullPage: opts.fullPage ?? true, animations: 'disabled' });
  return full;
}

/** Reset counters — primarily for tests that want deterministic numbering. */
export function resetScreenshotCounters(): void {
  counters.clear();
}

export { SCREENSHOT_ROOT };
