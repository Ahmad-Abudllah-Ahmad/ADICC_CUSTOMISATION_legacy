#!/usr/bin/env node
// One-off splitter: extracts each locale from i18n-fallbacks.ts into its own
// file under src/app/locales/{code}.ts. Run from the frontend/ directory:
//   node --experimental-strip-types scripts/split-i18n-fallbacks.mjs
//
// Idempotent — re-running overwrites the per-locale files but does NOT
// modify i18n-fallbacks.ts or i18n.ts. Those edits live in the release PR.

import { writeFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..');
const localesDir = resolve(repoRoot, 'src/app/locales');

const mod = await import(pathToFileURL(resolve(repoRoot, 'src/app/i18n-fallbacks.ts')).href);
const { fallbackResources } = mod;

const locales = Object.keys(fallbackResources);
console.log(`Found ${locales.length} locales: ${locales.join(', ')}`);

for (const code of locales) {
  const data = fallbackResources[code];
  const file = resolve(localesDir, `${code}.ts`);
  // JSON.stringify produces deterministic, double-quoted output. Wrapping in
  // a default-export const keeps consumer code as `import resource from
  // './locales/de'`. The file is parsed by Vite as a TS module; we set
  // `as const` and an explicit type so editors don't widen string values.
  const json = JSON.stringify(data, null, 2);
  const content = `// Auto-generated from i18n-fallbacks.ts split. Do not edit by hand.\n// Regenerate with: node --experimental-strip-types scripts/split-i18n-fallbacks.mjs\n\nconst resource = ${json} as { translation: Record<string, string> };\n\nexport default resource;\n`;
  await writeFile(file, content, 'utf8');
  const keyCount = Object.keys(data.translation).length;
  console.log(`  ${code}: ${keyCount} keys -> ${file.replace(repoRoot + '/', '')}`);
}

console.log('done');
