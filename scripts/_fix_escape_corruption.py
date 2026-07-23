# -*- coding: utf-8 -*-
"""‌⁠‍Fix the escape corruption introduced by earlier passes.

Earlier passes did `value.replace("\\\\", "\\\\\\\\")` which doubled all backslashes,
then escaped quotes again, producing `\\\\\\\\\"` where there should be just `\\\"`.
This pass detects and fixes such corruption.
"""
import re
from pathlib import Path

MN_PATH = Path("frontend/src/app/locales/mn.ts")
mn = MN_PATH.read_text(encoding="utf-8")

# Find any line with corruption pattern: \\\" (4 chars: \\, \, ") should be \" (2 chars: \, ")
# Simply: collapse `\\\\"` (4 chars in file = 4 chars `\`, `\`, `\`, `"`) into `\\"` (2 chars in file = `\`, `"`)
# In Python source: `\\\\\\\\\"` matches 4-char `\\\\\"` in file → becomes 2-char `\\"` in file
out = mn.replace('\\\\\\"', '\\"')
# Also any \\\\n that should be \n (Pass5 wrote raw Mongolian which is fine; this is for older corruption)

if out == mn:
    print("No corruption found")
else:
    diffs = sum(1 for c, o in zip(mn, out) if c != o)
    MN_PATH.write_text(out, encoding="utf-8")
    print(f"Fixed escape corruption: removed {len(mn) - len(out)} chars total")
