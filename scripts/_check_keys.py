# -*- coding: utf-8 -*-
"""‌⁠‍Check raw EN values for specific keys."""
import re
from pathlib import Path

en = Path("frontend/src/app/locales/en.ts").read_text(encoding="utf-8")
pat = re.compile(r'"((?:[^"\\]|\\.)+)"\s*:\s*"((?:[^"\\]|\\.)*)"')
en_pairs = {m.group(1): m.group(2) for m in pat.finditer(en)}

for k in ['ai.paste_placeholder', 'assemblies.what_are_assemblies', 'boq.ai_hint', 'files.email.sample_body', 'about.cap.costmodel_desc']:
    v = en_pairs.get(k, 'MISSING')
    print(f'{k}:')
    print(f'  raw: {v[:300]}')
    print(f'  repr: {repr(v[:300])}')
    print()
