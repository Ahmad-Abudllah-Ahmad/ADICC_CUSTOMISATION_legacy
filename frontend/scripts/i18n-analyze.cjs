// Analyze locale: count truly missing vs identical-to-EN vs translated (any non-identical)
const fs = require('fs');
const path = require('path');

function extract(f) {
  const src = fs.readFileSync(f, 'utf8');
  const start = src.indexOf('"translation": {');
  let i = start + '"translation": {'.length;
  let d = 1;
  const sb = i;
  while (i < src.length && d > 0) {
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
    if (c === '{') d++;
    else if (c === '}') d--;
    i++;
  }
  const body = src.slice(sb, i - 1);
  const pairs = {};
  let p = 0;
  while (p < body.length) {
    while (p < body.length && /[\s,]/.test(body[p])) p++;
    if (p >= body.length) break;
    if (body[p] !== '"') { p++; continue; }
    p++;
    let ks = p;
    while (p < body.length && body[p] !== '"') {
      if (body[p] === '\\') p += 2;
      else p++;
    }
    const key = body.slice(ks, p);
    p++;
    while (p < body.length && /[\s:]/.test(body[p])) p++;
    if (body[p] !== '"') {
      let dl = 0;
      while (p < body.length) {
        const c = body[p];
        if (c === '{' || c === '[') dl++;
        else if (c === '}' || c === ']') dl--;
        else if (c === ',' && dl === 0) break;
        p++;
      }
      continue;
    }
    p++;
    let vs = p;
    while (p < body.length && body[p] !== '"') {
      if (body[p] === '\\') p += 2;
      else p++;
    }
    pairs[key] = body.slice(vs, p);
    p++;
  }
  return pairs;
}

const locale = process.argv[2];
const mode = process.argv[3] || 'summary';
const en = extract(path.join(__dirname, '..', 'src', 'app', 'locales', 'en.ts'));
const t = extract(path.join(__dirname, '..', 'src', 'app', 'locales', `${locale}.ts`));

const missing = [];
const identical = [];
const translated = [];
for (const k of Object.keys(en)) {
  if (!(k in t)) missing.push(k);
  else if (t[k] === en[k]) identical.push(k);
  else translated.push(k);
}
const total = Object.keys(en).length;

if (mode === 'list-missing') {
  for (const k of missing) console.log(JSON.stringify({ key: k, en: en[k] }));
} else if (mode === 'list-identical') {
  for (const k of identical) console.log(JSON.stringify({ key: k, en: en[k] }));
} else if (mode === 'list-needs') {
  // both missing AND identical need work
  for (const k of [...missing, ...identical]) console.log(JSON.stringify({ key: k, en: en[k] }));
} else {
  console.log(`Locale: ${locale}`);
  console.log(`Total EN keys: ${total}`);
  console.log(`Translated (different from EN): ${translated.length} (${(translated.length / total * 100).toFixed(2)}%)`);
  console.log(`Identical to EN (likely untranslated): ${identical.length}`);
  console.log(`Missing in locale: ${missing.length}`);
  console.log(`Need-to-translate: ${missing.length + identical.length}`);
}
