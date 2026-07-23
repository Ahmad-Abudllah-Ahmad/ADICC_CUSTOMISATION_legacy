# -*- coding: utf-8 -*-
"""‌⁠‍Show translated examples for each prefix to understand existing style."""
import re
from pathlib import Path

en = Path("frontend/src/app/locales/en.ts").read_text(encoding="utf-8")
mn = Path("frontend/src/app/locales/mn.ts").read_text(encoding="utf-8")

pat = re.compile(r'"((?:[^"\\]|\\.)+)"\s*:\s*"((?:[^"\\]|\\.)*)"')
en_pairs = {m.group(1): m.group(2) for m in pat.finditer(en)}
mn_pairs = {m.group(1): m.group(2) for m in pat.finditer(mn)}


def has_cyrillic(s):
    return any("Ѐ" <= c <= "ӿ" for c in s)


# Show translated examples grouped by prefix
import sys
prefixes = sys.argv[1:] if len(sys.argv) > 1 else ['about', 'boq', 'tendering', 'risk', 'projects', 'common', 'nav', 'auth', 'login', 'errors']
for prefix in prefixes:
    print(f'\n=== {prefix} (translated examples) ===')
    count = 0
    for k, v in mn_pairs.items():
        if k.startswith(prefix + '.') and v != en_pairs.get(k, '') and has_cyrillic(v):
            en_v = en_pairs.get(k, '')
            print(f'  EN: {en_v[:100]}')
            print(f'  MN: {v[:100]}')
            print()
            count += 1
            if count >= 4:
                break
