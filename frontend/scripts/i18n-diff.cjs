// Temporary i18n diff tool — lists keys missing or English-equal in target locale vs en.ts
// Run: node frontend/scripts/i18n-diff.cjs <target-locale-file> [list-missing|list-untranslated|list-keys]
const fs = require('fs');
const path = require('path');

function extractResource(filePath) {
  const src = fs.readFileSync(filePath, 'utf8');
  const startMarker = '"translation": {';
  const startIdx = src.indexOf(startMarker);
  if (startIdx < 0) throw new Error('translation block not found in ' + filePath);
  let i = startIdx + startMarker.length;
  let depth = 1;
  const startBody = i;
  while (i < src.length && depth > 0) {
    const c = src[i];
    if (c === '"') {
      i++;
      while (i < src.length) {
        if (src[i] === '\\') { i += 2; continue; }
        if (src[i] === '"') break;
        i++;
      }
      i++;
      continue;
    }
    if (c === '{') depth++;
    else if (c === '}') depth--;
    i++;
  }
  const bodyEnd = i - 1;
  const body = src.slice(startBody, bodyEnd);

  const pairs = {};
  let p = 0;
  while (p < body.length) {
    while (p < body.length && /[\s,]/.test(body[p])) p++;
    if (p >= body.length) break;
    if (body[p] !== '"') { p++; continue; }
    p++;
    let keyStart = p;
    while (p < body.length && body[p] !== '"') {
      if (body[p] === '\\') p += 2;
      else p++;
    }
    const key = body.slice(keyStart, p);
    p++;
    while (p < body.length && /[\s:]/.test(body[p])) p++;
    if (body[p] !== '"') {
      let depthLocal = 0;
      while (p < body.length) {
        const c = body[p];
        if (c === '{' || c === '[') depthLocal++;
        else if (c === '}' || c === ']') depthLocal--;
        else if (c === ',' && depthLocal === 0) break;
        p++;
      }
      continue;
    }
    p++;
    let valStart = p;
    while (p < body.length && body[p] !== '"') {
      if (body[p] === '\\') p += 2;
      else p++;
    }
    const value = body.slice(valStart, p);
    p++;
    pairs[key] = value;
  }
  return pairs;
}

const enPath = path.join(__dirname, '..', 'src', 'app', 'locales', 'en.ts');
const target = process.argv[2];
if (!target) {
  console.error('Usage: node i18n-diff.cjs <target-locale-file>');
  process.exit(1);
}
const targetPath = path.resolve(target);
const en = extractResource(enPath);
const tgt = extractResource(targetPath);

const enKeys = Object.keys(en);
const missing = [];
const englishEqual = [];
const translated = [];

for (const k of enKeys) {
  if (!(k in tgt)) {
    missing.push(k);
  } else if (tgt[k] === en[k] && /[A-Za-z]/.test(en[k]) && en[k].length > 1) {
    englishEqual.push(k);
  } else {
    translated.push(k);
  }
}

const total = enKeys.length;
const cov = translated.length / total;

const mode = process.argv[3] || 'summary';
if (mode === 'list-missing') {
  for (const k of [...missing, ...englishEqual]) {
    const v = (en[k] || '').replace(/\n/g, '\\n');
    console.log(JSON.stringify({ key: k, en: v }));
  }
} else if (mode === 'list-only-missing') {
  for (const k of missing) {
    const v = (en[k] || '').replace(/\n/g, '\\n');
    console.log(JSON.stringify({ key: k, en: v }));
  }
} else if (mode === 'list-only-english') {
  for (const k of englishEqual) {
    const v = (en[k] || '').replace(/\n/g, '\\n');
    console.log(JSON.stringify({ key: k, en: v, current: tgt[k] }));
  }
} else if (mode === 'list-keys') {
  for (const k of [...missing, ...englishEqual]) console.log(k);
} else {
  console.log(`File: ${path.basename(targetPath)}`);
  console.log(`Total EN keys:   ${total}`);
  console.log(`Translated:      ${translated.length} (${(cov*100).toFixed(2)}%)`);
  console.log(`English-equal:   ${englishEqual.length}`);
  console.log(`Missing in tgt:  ${missing.length}`);
  console.log(`Need-to-fix:     ${missing.length + englishEqual.length}`);
}
