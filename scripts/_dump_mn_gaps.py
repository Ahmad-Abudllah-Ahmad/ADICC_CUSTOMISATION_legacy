# -*- coding: utf-8 -*-
"""‌⁠‍Dump all untranslated mn keys as a JSON file for translation pipeline."""
import json
import re
from pathlib import Path

en = Path("frontend/src/app/locales/en.ts").read_text(encoding="utf-8")
mn = Path("frontend/src/app/locales/mn.ts").read_text(encoding="utf-8")

pat = re.compile(r'"((?:[^"\\]|\\.)+)"\s*:\s*"((?:[^"\\]|\\.)*)"')
en_pairs = {m.group(1): m.group(2) for m in pat.finditer(en)}
mn_pairs = {m.group(1): m.group(2) for m in pat.finditer(mn)}

untranslated = {k: en_pairs[k] for k in en_pairs if k in mn_pairs and mn_pairs[k] == en_pairs[k] and en_pairs[k]}

Path("scripts/_mn_untranslated.json").write_text(
    json.dumps(untranslated, indent=2, ensure_ascii=False, sort_keys=True),
    encoding="utf-8",
)
print(f"Wrote {len(untranslated)} untranslated entries.")
