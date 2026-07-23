# -*- coding: utf-8 -*-
"""‌⁠‍Dump remaining untranslated entries."""
import re
import json
from pathlib import Path
from collections import defaultdict

en = Path("frontend/src/app/locales/en.ts").read_text(encoding="utf-8")
mn = Path("frontend/src/app/locales/mn.ts").read_text(encoding="utf-8")

pat = re.compile(r'"((?:[^"\\]|\\.)+)"\s*:\s*"((?:[^"\\]|\\.)*)"')
en_pairs = {m.group(1): m.group(2) for m in pat.finditer(en)}
mn_pairs = {m.group(1): m.group(2) for m in pat.finditer(mn)}

untranslated = {k: en_pairs[k] for k in en_pairs if k in mn_pairs and mn_pairs[k] == en_pairs[k] and en_pairs[k]}

with open("scripts/_mn_remaining.json", "w", encoding="utf-8") as f:
    json.dump(untranslated, f, indent=2, ensure_ascii=False)

print(f"Remaining: {len(untranslated)}")

# Group by prefix
by_prefix = defaultdict(int)
for k in untranslated:
    by_prefix[k.split(".")[0]] += 1
for prefix, count in sorted(by_prefix.items(), key=lambda x: -x[1]):
    print(f"  {prefix}: {count}")
