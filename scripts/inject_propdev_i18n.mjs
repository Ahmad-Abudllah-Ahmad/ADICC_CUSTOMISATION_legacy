#!/usr/bin/env node
/**
 * One-shot injector: writes a `propdev.*` block of flat dotted keys
 * into every locale file under frontend/src/app/locales/, immediately
 * before the closing `}` of the `translation` object.
 *
 * Idempotent: if a `propdev.title` key already exists in the file,
 * the existing propdev block is replaced (delimited by sentinel
 * comments) rather than duplicated.
 *
 * Run: node scripts/inject_propdev_i18n.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const LOCALES_DIR = path.join(__dirname, '..', 'frontend', 'src', 'app', 'locales');

// Master key order — keep stable so diffs are reviewable.
const KEY_ORDER = [
  'title', 'subtitle', 'new_development', 'new_plot', 'new_house_type', 'new_buyer',
  'pipeline_intro', 'step_dev', 'step_buyers', 'step_contracts', 'step_finance',
  'developments', 'plots', 'house_types', 'buyers', 'handovers', 'warranty',
  'untitled',
  'load_error',
  'empty_developments', 'empty_developments_desc',
  'plots_sold', 'contracted', 'open_snags',
  'empty_plots', 'empty_plots_desc',
  'empty_house_types', 'empty_house_types_desc',
  'area', 'levels', 'base_price', 'variants',
  'empty_buyers', 'empty_buyers_desc',
  'buyer', 'email', 'stage', 'contract_value', 'freeze_deadline',
  'in_days', 'overdue_days',
  'empty_handovers', 'empty_handovers_desc',
  'plot_n', 'no_buyer', 'no_handovers', 'completed', 'scheduled', 'snags',
  'warranty_updated', 'warranty_needs_buyer',
  'no_claims', 'no_claims_desc',
  'plot', 'category', 'description', 'status',
  'accept', 'reject', 'close',
  'built', 'house_type', 'orientation', 'garden', 'reserved_until',
  'plot_reserved', 'reserve_plot', 'full_name', 'reserve',
  'signed', 'deposit', 'days_overdue', 'days_left',
  'selections', 'no_selections',
  'stage_lead', 'stage_reserved', 'stage_contracted', 'stage_handover', 'stage_cancelled',
  'contract_signed', 'sign_contract', 'contract',
  'development_created', 'plot_created', 'house_type_created', 'buyer_created',
  'project', 'code', 'name', 'total_plots',
  'development', 'plot_number', 'bedrooms', 'phone',
];

// Per-locale translations. Each entry maps the bare key (without
// "propdev." prefix) to its native value. The English source is
// authoritative — every other locale must contain every key.
import { TRANSLATIONS } from './_propdev_translations.mjs';

const SENTINEL_START = '    // --- propdev (task #141) ---';
const SENTINEL_END = '    // --- /propdev ---';

function escapeJsonString(s) {
  // Encode as a JSON string literal (handles quotes, backslashes, control chars).
  return JSON.stringify(s);
}

function buildBlock(locale) {
  const trans = TRANSLATIONS[locale];
  if (!trans) throw new Error(`No translations defined for locale: ${locale}`);
  const lines = [SENTINEL_START];
  for (const k of KEY_ORDER) {
    const v = trans[k];
    if (v == null) throw new Error(`Missing translation for ${locale}: ${k}`);
    lines.push(`    "propdev.${k}": ${escapeJsonString(v)},`);
  }
  lines.push(SENTINEL_END);
  return lines.join('\n');
}

function injectIntoFile(filePath, locale) {
  let text = fs.readFileSync(filePath, 'utf8');
  const block = buildBlock(locale);

  // If a previous block exists, replace it in-place.
  if (text.includes(SENTINEL_START)) {
    const escRe = /[.*+?^${}()|[\]\\]/g;
    const re = new RegExp(
      `${SENTINEL_START.replace(escRe, '\\$&')}[\\s\\S]*?${SENTINEL_END.replace(escRe, '\\$&')}`,
      'm',
    );
    text = text.replace(re, block);
    fs.writeFileSync(filePath, text, 'utf8');
    return 'replaced';
  }

  // Otherwise insert just before the closing `}` of the translation object.
  // Pattern: matches the closing brace of "translation" obj — the line `  }`
  // immediately followed by `} as { translation: ...`.
  const closingRe = /(\n)(\s*\})(\s*\n\}\s+as\s+\{\s+translation)/;
  if (!closingRe.test(text)) {
    throw new Error(`Could not locate translation object close in ${filePath}`);
  }
  text = text.replace(closingRe, `$1${block}\n$2$3`);
  fs.writeFileSync(filePath, text, 'utf8');
  return 'inserted';
}

const LOCALES = Object.keys(TRANSLATIONS).sort();
let inserted = 0, replaced = 0;
for (const loc of LOCALES) {
  const fp = path.join(LOCALES_DIR, `${loc}.ts`);
  if (!fs.existsSync(fp)) {
    console.warn(`SKIP ${loc}: file not found at ${fp}`);
    continue;
  }
  const result = injectIntoFile(fp, loc);
  if (result === 'inserted') inserted++; else replaced++;
  console.log(`${result.padEnd(8)} ${loc}.ts (${KEY_ORDER.length} keys)`);
}
console.log(`\nDone. ${inserted} inserted, ${replaced} replaced, ${KEY_ORDER.length} keys/locale.`);
