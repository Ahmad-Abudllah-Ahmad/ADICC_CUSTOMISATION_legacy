"""Strip zero-width Unicode characters from source files.

Used by R6 zero-width regression fix (task #135). Also reusable as a
maintenance helper if rogue characters reappear.

Strips the following codepoints:
  U+200B ZERO WIDTH SPACE
  U+200C ZERO WIDTH NON-JOINER
  U+200D ZERO WIDTH JOINER
  U+200E LEFT-TO-RIGHT MARK
  U+200F RIGHT-TO-LEFT MARK
  U+2060 WORD JOINER
  U+2061-U+2064 INVISIBLE OPERATORS
  U+2066-U+2069 BIDI ISOLATES
  U+FEFF ZERO WIDTH NO-BREAK SPACE

Preserves:
  * frontend/src/app/locales/ar.ts (U+200E inside Arabic RTL content is
    linguistically meaningful).

Note: a few JS regex literals embed literal ZW chars next to their
escape-sequence equivalents (e.g.
`replace(/[\\u200b-\\u200f\\u2060\\ufeff]/g, '')`). Stripping the literal
chars leaves the equivalent escape-only regex intact and still correct,
so we do not special-case these.
"""

from __future__ import annotations

import os
import sys

ZW_CHARS = {
    "​": "U+200B ZWSP",
    "‌": "U+200C ZWNJ",
    "‍": "U+200D ZWJ",
    "‎": "U+200E LRM",
    "‏": "U+200F RLM",
    "⁠": "U+2060 WJ",
    "⁡": "U+2061 FA",
    "⁢": "U+2062 IT",
    "⁣": "U+2063 IS",
    "⁤": "U+2064 IP",
    "⁦": "U+2066 LRI",
    "⁧": "U+2067 RLI",
    "⁨": "U+2068 FSI",
    "⁩": "U+2069 PDI",
    "﻿": "U+FEFF BOM",
}

TARGETS = [
    ("frontend/src", (".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".md", ".snap")),
    ("marketing-site", (".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".md", ".py")),
]

PRESERVE_FILES = {
    os.path.normpath("frontend/src/app/locales/ar.ts"),
}


def strip_file(path: str, stats: dict[str, int]) -> bool:
    """Strip in place; return True if file changed."""
    with open(path, "r", encoding="utf-8", newline="") as fh:
        data = fh.read()
    if not any(c in data for c in ZW_CHARS):
        return False

    new_data = data
    for ch in ZW_CHARS:
        n = new_data.count(ch)
        if n:
            stats[ch] = stats.get(ch, 0) + n
            new_data = new_data.replace(ch, "")

    if new_data != data:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_data)
        return True
    return False


def main() -> int:
    stats: dict[str, int] = {}
    files_modified: list[str] = []
    files_preserved: list[tuple[str, str]] = []
    total_audited = 0

    for base, exts in TARGETS:
        if not os.path.isdir(base):
            continue
        for dirpath, _, files in os.walk(base):
            norm_dir = dirpath.replace(os.sep, "/")
            if "/node_modules" in norm_dir or "/dist" in norm_dir:
                continue
            for f in files:
                if not f.endswith(exts):
                    continue
                p = os.path.normpath(os.path.join(dirpath, f))
                total_audited += 1
                if p in PRESERVE_FILES:
                    files_preserved.append(
                        (p, "Arabic LRM inside RTL text — linguistically required")
                    )
                    continue
                if strip_file(p, stats):
                    files_modified.append(p)

    sys.stdout.reconfigure(encoding="utf-8")
    print(f"TOTAL FILES AUDITED: {total_audited}")
    print(f"FILES MODIFIED: {len(files_modified)}")
    print(f"FILES PRESERVED: {len(files_preserved)}")
    for fp, reason in files_preserved:
        print(f"  PRESERVED: {fp} ({reason})")

    print("\nSTRIPPED COUNTS BY CHARACTER:")
    for ch, name in ZW_CHARS.items():
        if stats.get(ch):
            print(f"  {name}: {stats[ch]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
