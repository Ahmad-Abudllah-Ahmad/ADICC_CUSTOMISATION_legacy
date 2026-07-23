# -*- coding: utf-8 -*-
import re
from pathlib import Path

en = Path("frontend/src/app/locales/en.ts").read_text(encoding="utf-8")
mn = Path("frontend/src/app/locales/mn.ts").read_text(encoding="utf-8")
pat = re.compile(r'"((?:[^"\\]|\\.)+)"\s*:\s*"((?:[^"\\]|\\.)*)"')
en_pairs = {m.group(1): m.group(2) for m in pat.finditer(en)}
mn_pairs = {m.group(1): m.group(2) for m in pat.finditer(mn)}

identical = sorted([k for k in en_pairs if k in mn_pairs and en_pairs[k] == mn_pairs[k] and en_pairs[k]])
print(f"Identical: {len(identical)}")
for k in identical:
    print(f"  {k}: {en_pairs[k]!r}")
