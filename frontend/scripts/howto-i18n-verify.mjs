// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
//
// Independently verify the per-locale How-it-works translation files against
// the English key set. Catches truncated / short / corrupt files before they
// are applied into the locale source-of-truth.
//
//   node scripts/howto-i18n-verify.mjs

import { readdirSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const dir = join(here, '.howto-i18n');

/** Read a JSON file that may be UTF-16LE (PowerShell `>`) or UTF-8 (+/- BOM). */
function readJson(path) {
  const raw = readFileSync(path);
  let text;
  if (raw[0] === 0xff && raw[1] === 0xfe) text = raw.toString('utf16le');
  else text = raw.toString('utf8');
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1); // strip BOM
  return JSON.parse(text);
}

let refKeys = null;
try {
  refKeys = new Set(Object.keys(readJson(join(dir, 'en.json'))));
} catch (e) {
  process.stderr.write(`en.json: REFERENCE PARSE FAIL - ${e.message}\n`);
}
const expected = refKeys ? refKeys.size : 850;

const files = readdirSync(dir)
  .filter((f) => /^[a-z]{2}\.json$/.test(f) && f !== 'en.json')
  .sort();

let ok = 0;
let bad = 0;
for (const f of files) {
  const code = f.replace('.json', '');
  try {
    const obj = readJson(join(dir, f));
    const keys = Object.keys(obj);
    let missing = 0;
    let extra = 0;
    let empty = 0;
    if (refKeys) {
      for (const k of refKeys) if (!(k in obj)) missing++;
      for (const k of keys) if (!refKeys.has(k)) extra++;
    }
    for (const k of keys) if (typeof obj[k] !== 'string' || obj[k] === '') empty++;
    const good = keys.length === expected && missing === 0 && extra === 0 && empty === 0;
    if (good) ok++;
    else bad++;
    process.stdout.write(
      `${good ? 'OK  ' : 'BAD '} ${code}: ${keys.length}/${expected} keys, ` +
        `missing ${missing}, extra ${extra}, empty ${empty}\n`,
    );
  } catch (e) {
    bad++;
    process.stdout.write(`BAD  ${code}: PARSE ERROR - ${e.message}\n`);
  }
}
process.stdout.write(`\n${files.length} locale files | ${ok} OK | ${bad} need attention\n`);
