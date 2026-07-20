// Walk every marketing page on the live VPS and save full-page
// screenshots at desktop + mobile widths so we can audit layout
// without manual clicking.

import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(__dirname, 'shots');
mkdirSync(OUT_DIR, { recursive: true });

const BASE = process.env.BASE_URL || 'https://adicc-uae.com';
const PAGES = ['/', '/services.html', '/industries.html', '/standards.html', '/maturity.html'];
const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile',  width: 390,  height: 844 },
];

const browser = await chromium.launch();
try {
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      deviceScaleFactor: 1,
    });
    const page = await ctx.newPage();
    for (const path of PAGES) {
      const url = `${BASE}${path}`;
      const slug = (path === '/' ? 'home' : path.replace(/^\/|\.html$/g, ''));
      const file = join(OUT_DIR, `${slug}.${vp.name}.png`);
      console.log(`-> ${vp.name} ${url}`);
      try {
        await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
        // give animations / fonts a beat
        await page.waitForTimeout(800);
        await page.screenshot({ path: file, fullPage: true });
      } catch (e) {
        console.error(`  FAIL ${url}: ${e.message}`);
      }
    }
    await ctx.close();
  }
} finally {
  await browser.close();
}
console.log('done.');
