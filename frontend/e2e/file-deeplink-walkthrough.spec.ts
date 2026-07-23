import { test, expect } from '@playwright/test';
import { loginV19 } from './v1.9/helpers-v19';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

// QA walkthrough: from /files, click a file of each kind and confirm the
// destination module actually opens that file (not just the bare module
// shell). Captures one screenshot per stop so a human reviewer can spot
// what's missing without running the test themselves.
//
// Targets the dev server on http://localhost:5180 because that's what's
// running on this machine. baseURL in playwright.config.ts is 5173, but
// we override per-spec.

const BASE = 'http://localhost:5180';
const __dirname_esm = path.dirname(fileURLToPath(import.meta.url));
const SHOTS_DIR = path.resolve(__dirname_esm, '../qa-shots/file-deeplink');

test.beforeAll(() => {
  fs.mkdirSync(SHOTS_DIR, { recursive: true });
});

test.use({ baseURL: BASE });

async function shot(page: import('@playwright/test').Page, name: string) {
  const file = path.join(SHOTS_DIR, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  console.log(`  → ${file}`);
}

test('file deeplink walkthrough — every kind', async ({ page }) => {
  test.setTimeout(120_000);

  await loginV19(page);
  await page.goto(`${BASE}/files`);
  await page.waitForLoadState('networkidle');
  await shot(page, '00-files-landing');

  // Try each kind filter in sequence. Each section is best-effort: if no
  // file of that kind exists we just shoot the empty state and move on.
  const kinds = ['document', 'photo', 'bim_model', 'dwg_drawing'] as const;

  for (const kind of kinds) {
    console.log(`\n=== kind=${kind} ===`);
    await page.goto(`${BASE}/files?kind=${kind}`);
    await page.waitForLoadState('networkidle');
    await shot(page, `01-${kind}-list`);

    // Find the first file row. The grid renders cards; the list view
    // renders <tr>. Either selector is fine — pick whichever resolves.
    const card = page.locator('[data-file-id]').first();
    const cardCount = await card.count();
    if (cardCount === 0) {
      console.log(`  no files of kind=${kind}, skipping click`);
      continue;
    }
    const fileId = await card.getAttribute('data-file-id');
    console.log(`  clicking file id=${fileId}`);
    await card.click();
    await page.waitForTimeout(500);
    await shot(page, `02-${kind}-preview`);

    // Look for the primary "Open in {Module}" CTA in the preview pane.
    const cta = page.locator('button:has-text("Open in"), a:has-text("Open in")').first();
    if (await cta.count() === 0) {
      console.log(`  no "Open in" CTA visible — pane might be collapsed`);
      continue;
    }
    await cta.click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);
    const url = page.url();
    console.log(`  navigated to: ${url}`);
    await shot(page, `03-${kind}-destination`);
  }
});
