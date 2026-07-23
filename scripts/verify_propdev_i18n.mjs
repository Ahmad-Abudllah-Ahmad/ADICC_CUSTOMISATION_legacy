#!/usr/bin/env node
/**
 * Verifies that every locale file under frontend/src/app/locales/
 * contains the complete `propdev.*` namespace defined by EN.
 *
 * Exit code 0 on success, non-zero if any locale is missing keys.
 * Intended to run in CI as a guard against translation drift.
 *
 * Run: node scripts/verify_propdev_i18n.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const LOCALES_DIR = path.join(__dirname, '..', 'frontend', 'src', 'app', 'locales');

const PROPDEV_KEY_RE = /"(propdev\.[a-z_]+)"\s*:/g;

function extractPropdevKeys(filePath) {
  const txt = fs.readFileSync(filePath, 'utf8');
  const keys = new Set();
  let m;
  while ((m = PROPDEV_KEY_RE.exec(txt)) !== null) keys.add(m[1]);
  return keys;
}

const files = fs.readdirSync(LOCALES_DIR).filter((f) => f.endsWith('.ts')).sort();
if (!files.includes('en.ts')) {
  console.error('FATAL: en.ts not found in', LOCALES_DIR);
  process.exit(2);
}

const enKeys = extractPropdevKeys(path.join(LOCALES_DIR, 'en.ts'));
console.log(`EN reference: ${enKeys.size} propdev.* keys`);

let allGood = true;
const report = [];
for (const f of files) {
  const locale = f.replace(/\.ts$/, '');
  const keys = extractPropdevKeys(path.join(LOCALES_DIR, f));
  const missing = [...enKeys].filter((k) => !keys.has(k));
  const extra = [...keys].filter((k) => !enKeys.has(k));
  const status = missing.length === 0 && extra.length === 0 ? 'OK' : 'FAIL';
  if (status !== 'OK') allGood = false;
  report.push({ locale, count: keys.size, missing: missing.length, extra: extra.length, status });
  if (missing.length > 0) {
    console.error(`  ${locale}: MISSING ${missing.length} keys: ${missing.slice(0, 5).join(', ')}${missing.length > 5 ? '…' : ''}`);
  }
  if (extra.length > 0) {
    console.error(`  ${locale}: EXTRA ${extra.length} keys: ${extra.slice(0, 5).join(', ')}${extra.length > 5 ? '…' : ''}`);
  }
}

// Compact table
console.log('\nCoverage table:');
console.log('locale  count  status');
console.log('------  -----  ------');
for (const r of report) {
  console.log(`${r.locale.padEnd(6)}  ${String(r.count).padStart(5)}  ${r.status}`);
}

if (allGood) {
  console.log(`\nAll ${files.length} locales have complete propdev.* coverage (${enKeys.size} keys each).`);
  process.exit(0);
}
console.error('\nSome locales are missing or have stray propdev.* keys.');
process.exit(1);
