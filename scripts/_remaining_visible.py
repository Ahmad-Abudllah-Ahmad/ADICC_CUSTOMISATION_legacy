"""‌⁠‍Dump remaining identicals per locale into a flat list grouped by key."""
import json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
report = json.loads((ROOT / 'scripts/_visible_gap.json').read_text(encoding='utf-8'))
en_vals = report['visible_keys']

# Re-run intersection: count per key
all_by_key = defaultdict(list)
for code, keys in report['per_locale_keys'].items():
    for k in keys:
        all_by_key[k].append(code)

# But the data is stale. Re-execute with current file state.
import re
PAIR = re.compile(r'"((?:[^"\\]|\\.)+)"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)


def parse_ts(path):
    return dict(PAIR.findall(Path(path).read_text(encoding='utf-8')))


locales = ['de', 'fr', 'es', 'it', 'pt', 'ru', 'zh', 'ja', 'ko', 'ar', 'hi',
           'th', 'vi', 'id', 'tr', 'nl', 'pl', 'cs', 'sv', 'no', 'da', 'fi',
           'ro', 'bg', 'hr', 'mn']

fresh_by_key = defaultdict(list)
for code in locales:
    d = parse_ts(ROOT / f'frontend/src/app/locales/{code}.ts')
    for k, v in en_vals.items():
        if d.get(k) == v:
            fresh_by_key[k].append(code)

# Filter out app.name/badges/file-extensions intentionally
NEUTRAL_KEYS = {'app.name', 'nav.mode_pro_badge', 'nav.mode_std_badge'}

actionable = {k: codes for k, codes in fresh_by_key.items() if k not in NEUTRAL_KEYS}
print(f"Total actionable visible keys still identical-to-EN somewhere: {len(actionable)}")
print(f"Cross-locale density: keys identical in >=20 locales:")
for k, codes in sorted(actionable.items(), key=lambda x: -len(x[1])):
    if len(codes) >= 5:
        print(f"  [{len(codes):2d}/26] {k} = {en_vals[k]!r}")

# Save for downstream patcher
out = ROOT / 'scripts/_remaining_visible.json'
out.write_text(json.dumps({
    'keys': {k: en_vals[k] for k in actionable},
    'codes_per_key': {k: c for k, c in actionable.items()},
}, indent=2, ensure_ascii=False), encoding='utf-8')
print(f"\nDumped to {out}")
