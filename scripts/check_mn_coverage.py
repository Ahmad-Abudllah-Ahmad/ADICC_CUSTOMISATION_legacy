"""‌⁠‍Measure real Mongolian translation coverage of mn.ts vs en.ts."""
import re
from pathlib import Path

en = Path("frontend/src/app/locales/en.ts").read_text(encoding="utf-8")
mn = Path("frontend/src/app/locales/mn.ts").read_text(encoding="utf-8")

# Match "key": "value", on a single line. JSON-style escaped quotes allowed.
pat = re.compile(r'"((?:[^"\\]|\\.)+)"\s*:\s*"((?:[^"\\]|\\.)*)"')

en_pairs = {m.group(1): m.group(2) for m in pat.finditer(en)}
mn_pairs = {m.group(1): m.group(2) for m in pat.finditer(mn)}

both = set(en_pairs) & set(mn_pairs)
missing = set(en_pairs) - set(mn_pairs)
extra = set(mn_pairs) - set(en_pairs)

# Cyrillic range covers Mongolian Cyrillic alphabet (incl. өүңь)
def has_cyrillic(s: str) -> bool:
    return any("Ѐ" <= c <= "ӿ" for c in s)

identical = [k for k in both if en_pairs[k] == mn_pairs[k] and en_pairs[k]]
translated = [k for k in both if has_cyrillic(mn_pairs[k]) and mn_pairs[k] != en_pairs[k]]
empty = [k for k in both if not en_pairs[k] and not mn_pairs[k]]
other = [k for k in both if k not in identical and k not in translated and k not in empty]

print(f"en.ts keys: {len(en_pairs)}")
print(f"mn.ts keys: {len(mn_pairs)}")
print(f"  missing in mn:    {len(missing)}")
print(f"  extra in mn:      {len(extra)}")
print()
print(f"Of the {len(both)} keys present in both files:")
print(f"  translated (Cyrillic, differs from en): {len(translated)}  ({100*len(translated)/len(both):.1f}%)")
print(f"  identical to English (untranslated):    {len(identical)}  ({100*len(identical)/len(both):.1f}%)")
print(f"  empty in both:                          {len(empty)}")
print(f"  other (ASCII but differs):              {len(other)}")
print()
if missing:
    print(f"First 5 missing keys: {sorted(missing)[:5]}")
if extra:
    print(f"First 5 extra keys: {sorted(extra)[:5]}")
print()
print("Sample of 5 'identical' (untranslated) keys + values:")
for k in sorted(identical)[:5]:
    print(f"  {k!r}: {en_pairs[k][:60]!r}")
