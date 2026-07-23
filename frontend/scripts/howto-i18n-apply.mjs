// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
//
// Apply translated How-it-works keys into the per-locale source-of-truth files
// under src/app/locales/<code>.ts. Text-based + idempotent: each key is
// inserted once, right after the `"translation": {` line, and skipped if it is
// already present. Safe to re-run.
//
// Reads every scripts/.howto-i18n/<code>.json produced by the extractor (en)
// and the per-locale translators.
//
//   node scripts/howto-i18n-apply.mjs

import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = join(here, '.howto-i18n');
const localesDir = join(here, '..', 'src', 'app', 'locales');

const files = readdirSync(dataDir).filter((f) => /^[a-z]{2}\.json$/.test(f));
const report = [];

for (const f of files.sort()) {
  const code = f.replace('.json', '');
  const localeFile = join(localesDir, `${code}.ts`);
  let map;
  try {
    let rawJson = readFileSync(join(dataDir, f), 'utf8');
    if (rawJson.charCodeAt(0) === 0xfeff) rawJson = rawJson.slice(1); // strip BOM
    map = JSON.parse(rawJson);
  } catch (e) {
    report.push(`${code}: ERROR bad JSON (${e.message})`);
    continue;
  }
  // Read the locale file directly and treat a read failure as "absent", rather
  // than probing with existsSync first - a check-then-use pair is a file-system
  // race (the file can change between the two calls).
  let text;
  try {
    text = readFileSync(localeFile, 'utf8');
  } catch {
    report.push(`${code}: SKIP (no locale file)`);
    continue;
  }
  const idx = text.indexOf('"translation": {');
  if (idx === -1) {
    report.push(`${code}: ERROR no translation block`);
    continue;
  }
  const insertAt = text.indexOf('\n', idx) + 1;
  const lines = [];
  let added = 0;
  let skipped = 0;
  for (const [k, v] of Object.entries(map)) {
    if (typeof v !== 'string') {
      skipped++;
      continue;
    }
    if (text.includes(`${JSON.stringify(k)}:`)) {
      skipped++;
      continue;
    }
    lines.push(`    ${JSON.stringify(k)}: ${JSON.stringify(v)},`);
    added++;
  }
  if (added > 0) {
    text = text.slice(0, insertAt) + lines.join('\n') + '\n' + text.slice(insertAt);
    writeFileSync(localeFile, text, 'utf8');
  }
  report.push(`${code}: +${added} added, ${skipped} skipped (${Object.keys(map).length} in map)`);
}

for (const r of report) process.stderr.write(r + '\n');
