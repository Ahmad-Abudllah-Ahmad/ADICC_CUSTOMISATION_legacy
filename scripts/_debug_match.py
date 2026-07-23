# -*- coding: utf-8 -*-
import re
from pathlib import Path

en = Path("frontend/src/app/locales/en.ts").read_text(encoding="utf-8")
pat = re.compile(r'"((?:[^"\\]|\\.)+)"\s*:\s*"((?:[^"\\]|\\.)*)"')
en_pairs = {m.group(1): m.group(2) for m in pat.finditer(en)}

key = 'assemblies.what_are_assemblies'
v = en_pairs[key]

# My dict key:
my_key = "Assemblies are reusable cost recipes that combine multiple resources (materials, labor, equipment) into a single composite rate. For example, a \\\"Reinforced Concrete Wall\\\" assembly includes concrete, rebar, formwork, and labor. Apply assemblies to BOQ positions to auto-populate component costs."

print(f"en val repr: {repr(v[:120])}")
print(f"my key repr: {repr(my_key[:120])}")
print(f"match: {v == my_key}")

# What about boq.ai_hint
key2 = 'boq.ai_hint'
v2 = en_pairs[key2]
my_key2 = "Ask me to generate BOQ positions. For example: \\\"Add MEP items for a 5-story office building\\\""
print()
print(f"en val 2 repr: {repr(v2)}")
print(f"my key 2 repr: {repr(my_key2)}")
print(f"match: {v2 == my_key2}")
