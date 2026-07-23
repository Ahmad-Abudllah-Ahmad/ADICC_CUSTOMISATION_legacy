// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
//
// Extract every How-it-works i18n key + its inline English default into a flat
// JSON map, so the per-locale translators have an exact, complete key list.
//
// Run from the frontend/ directory:
//   node scripts/howto-i18n-extract.mjs > scripts/.howto-i18n/en.json
//
// Uses esbuild (already a dependency) to bundle the catalog so we read the
// REAL exported data rather than regex-parsing TypeScript. The catalog content
// lives in the per-domain files under src/features/help/catalog/*, flattened by
// src/features/help/moduleExplanations.ts. The page chrome keys (search box,
// headings, buttons) live inline in HowItWorksPage.tsx and are listed here.

import { build } from 'esbuild';
import { pathToFileURL } from 'node:url';
import { writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

/** Page chrome + spotlight keys defined inline in HowItWorksPage.tsx / Header. */
const CHROME = {
  'howto.eyebrow': 'Help center',
  'howto.page_title': 'How it works',
  'howto.page_subtitle':
    'A plain-language guide to every module: what it does, how to use it step by step, and where to find it. Search below, expand any card to learn more, or use "Show me where" to have the app point it out for you.',
  'howto.search_placeholder': 'Search modules - e.g. "cost", "schedule", "clash"...',
  'howto.result_count': '{{count}} of {{total}} modules',
  'howto.total_count': '{{total}} modules explained',
  'howto.no_results': 'No modules match your search.',
  'howto.beta': 'Beta',
  'howto.how_heading': 'How it works',
  'howto.when_heading': 'When to use it: ',
  'howto.show_me': 'Show me where',
  'howto.open_module': 'Open module',
  'howto.locate.title': 'Where to find it',
  'howto.locate.open': 'Open this module',
  'howto.menu_item': 'How it works',
};

const result = await build({
  entryPoints: ['src/features/help/moduleExplanations.ts'],
  bundle: true,
  format: 'esm',
  platform: 'node',
  write: false,
  logLevel: 'silent',
});

const dir = mkdtempSync(join(tmpdir(), 'howto-i18n-'));
const bundleFile = join(dir, 'catalog.mjs');
writeFileSync(bundleFile, result.outputFiles[0].text);
const mod = await import(pathToFileURL(bundleFile).href);

const MODULE_EXPLANATIONS = mod.MODULE_EXPLANATIONS ?? [];
const HOW_IT_WORKS_CATEGORIES = mod.HOW_IT_WORKS_CATEGORIES ?? [];

const out = {};
const put = (key, value) => {
  if (key && typeof value === 'string') out[key] = value;
};

for (const [k, v] of Object.entries(CHROME)) put(k, v);
for (const c of HOW_IT_WORKS_CATEGORIES) {
  put(c.labelKey, c.labelDefault);
  put(c.descKey, c.descDefault);
}
for (const m of MODULE_EXPLANATIONS) {
  put(m.titleKey, m.titleDefault);
  put(m.summaryKey, m.summaryDefault);
  put(m.whatKey, m.whatDefault);
  for (const s of m.how ?? []) put(s.key, s.default);
  for (const s of m.tips ?? []) put(s.key, s.default);
  if (m.whenKey && m.whenDefault) put(m.whenKey, m.whenDefault);
}

const sorted = {};
for (const k of Object.keys(out).sort()) sorted[k] = out[k];

process.stdout.write(JSON.stringify(sorted, null, 2) + '\n');
process.stderr.write(
  `howto-i18n-extract: ${Object.keys(sorted).length} keys from ${MODULE_EXPLANATIONS.length} modules\n`,
);
