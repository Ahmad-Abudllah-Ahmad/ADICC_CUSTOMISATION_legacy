# -*- coding: utf-8 -*-
"""‌⁠‍Analyze what's left untranslated in mn.ts."""
import re
from pathlib import Path
from collections import Counter

en = Path("frontend/src/app/locales/en.ts").read_text(encoding="utf-8")
mn = Path("frontend/src/app/locales/mn.ts").read_text(encoding="utf-8")

pat = re.compile(r'"((?:[^"\\]|\\.)+)"\s*:\s*"((?:[^"\\]|\\.)*)"')
en_pairs = {m.group(1): m.group(2) for m in pat.finditer(en)}
mn_pairs = {m.group(1): m.group(2) for m in pat.finditer(mn)}

untranslated = [k for k in en_pairs if k in mn_pairs and mn_pairs[k] == en_pairs[k] and en_pairs[k]]

# Group by prefix (first dot segment)
prefix_count = Counter(k.split(".")[0] for k in untranslated)
print("Untranslated count by prefix:")
for prefix, count in prefix_count.most_common():
    print(f"  {prefix}: {count}")

# Length distribution
short = [k for k in untranslated if len(en_pairs[k]) <= 30]
medium = [k for k in untranslated if 30 < len(en_pairs[k]) <= 100]
long_ = [k for k in untranslated if len(en_pairs[k]) > 100]
print(f"\nLength: short(<=30)={len(short)}, medium(31-100)={len(medium)}, long(>100)={len(long_)}")

print("\n=== Sample short ===")
for k in short[:30]:
    print(f"  {k!r}: {en_pairs[k]!r}")

print("\n=== Sample medium ===")
for k in medium[:20]:
    print(f"  {k!r}: {en_pairs[k]!r}")

print("\n=== Sample long ===")
for k in long_[:10]:
    print(f"  {k!r}: {en_pairs[k][:150]!r}")
