# -*- coding: utf-8 -*-
"""‌⁠‍Show sample translations to verify quality."""
import re
from pathlib import Path

en = Path("frontend/src/app/locales/en.ts").read_text(encoding="utf-8")
mn = Path("frontend/src/app/locales/mn.ts").read_text(encoding="utf-8")

pat = re.compile(r'"((?:[^"\\]|\\.)+)"\s*:\s*"((?:[^"\\]|\\.)*)"')
en_pairs = {m.group(1): m.group(2) for m in pat.finditer(en)}
mn_pairs = {m.group(1): m.group(2) for m in pat.finditer(mn)}

import sys
if len(sys.argv) > 1:
    keys = sys.argv[1:]
else:
    keys = [
        'about.intro', 'about.title', 'auth.forgot_subtitle',
        'common.filters', 'boq.accept', 'boq.add_to_root',
        'risk.run', 'tendering.packages', 'projects.boq_count',
        'nav.assets', 'meetings.page_title',
        'rfi.action_close', 'punch.action_start',
    ]

for k in keys:
    if k in mn_pairs:
        print(f'\n  KEY: {k}')
        print(f'  EN:  {en_pairs.get(k, "?")[:200]}')
        print(f'  MN:  {mn_pairs[k][:200]}')
