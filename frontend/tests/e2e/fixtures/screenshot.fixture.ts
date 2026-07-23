/**
 * screenshot.fixture.ts — auto-named screenshot capture.
 *
 * Replaces the manual `page.screenshot({ path: ... })` boilerplate with
 * a `captureScreen(name)` helper that:
 *   - Routes images to `qa-screenshots/<module>/<module>-<test>-<step>.png`
 *   - Auto-numbers steps within a test (01, 02, 03...)
 *   - Slugifies test titles and module names safely for FS use
 *   - Records the screenshot path as an attachment so the HTML report links to it
 *
 * Module is derived from the spec's directory:
 *   tests/e2e/smoke/auth.spec.ts → module = 'smoke'
 *   tests/e2e/boq/positions.spec.ts → module = 'boq'
 *
 * Override per-test with `test.use({ screenshotModule: 'custom' })` or by
 * placing tests in the right folder.
 */
import { test as base, type Page, type TestInfo } from '@playwright/test';
import { test as tenantTest } from './tenant.fixture';
import fs from 'node:fs';
import path from 'node:path';

const SCREENSHOT_ROOT = path.resolve(process.cwd(), 'qa-screenshots');

function slugify(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64);
}

function deriveModule(testInfo: TestInfo): string {
  // testInfo.file = absolute path; pick the first segment under tests/e2e/.
  const rel = path.relative(path.join(process.cwd(), 'tests/e2e'), testInfo.file);
  const first = rel.split(/[\\/]/)[0];
  return first && first !== '..' ? slugify(first) : 'misc';
}

export interface ScreenshotHelper {
  /** Capture a full-page screenshot with auto-numbering. */
  (name: string, opts?: { fullPage?: boolean; clip?: { x: number; y: number; width: number; height: number } }): Promise<string>;
  /** Current step counter (read-only). */
  readonly step: number;
}

function makeHelper(page: Page, testInfo: TestInfo): ScreenshotHelper {
  const module = (testInfo as TestInfo & { _screenshotModule?: string })._screenshotModule
    ?? deriveModule(testInfo);
  const testSlug = slugify(testInfo.title);
  const moduleDir = path.join(SCREENSHOT_ROOT, module);
  fs.mkdirSync(moduleDir, { recursive: true });

  let counter = 0;

  const fn = (async (name: string, opts?: { fullPage?: boolean; clip?: { x: number; y: number; width: number; height: number } }) => {
    counter += 1;
    const num = String(counter).padStart(2, '0');
    const file = `${module}-${testSlug}-${num}-${slugify(name)}.png`;
    const full = path.join(moduleDir, file);
    await page.screenshot({
      path: full,
      fullPage: opts?.fullPage ?? true,
      clip: opts?.clip,
      animations: 'disabled',
    });
    await testInfo.attach(file, { path: full, contentType: 'image/png' });
    return full;
  }) as ScreenshotHelper;

  Object.defineProperty(fn, 'step', { get: () => counter });
  return fn;
}

type ScreenshotFixtures = {
  captureScreen: ScreenshotHelper;
};

export const test = tenantTest.extend<ScreenshotFixtures>({
  captureScreen: async ({ page }, use, testInfo) => {
    await use(makeHelper(page, testInfo));
  },
});

export { expect } from '@playwright/test';
export { SCREENSHOT_ROOT };
