"""‌⁠‍Insert-or-replace v3.0 18-Modules Wave nav.* keys in 25 non-EN, non-MN locales.

Previous replace-only patch (patch_nav_v3_modules.py) ran successfully twice,
but each run was wiped by an external `git reset --hard HEAD` (reflog 08:20
and 09:00 today). After the resets the locale files no longer contain the
nav.* v3 module keys at all — they were never committed.

This script uses INSERT semantics: for each key, if absent, append it just
before the closing of the "translation" object. Format matches the existing
`    "key": "value",` indentation pattern used throughout each locale file.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Reuse the full translation table from patch_nav_v3_modules.py
import importlib.util
spec = importlib.util.spec_from_file_location(
    "patch_nav_v3_modules",
    ROOT / "scripts/patch_nav_v3_modules.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
TRANSLATIONS = mod.TRANSLATIONS


def patch_locale(code: str) -> tuple[int, int, int]:
    """‌⁠‍Return (inserted, replaced, skipped)."""
    path = ROOT / f'frontend/src/app/locales/{code}.ts'
    text = path.read_text(encoding='utf-8')
    original = text
    inserted = replaced = skipped = 0

    # Find an anchor: pick a nav.* key that exists in the file
    # Insert new keys immediately AFTER this anchor
    anchor_match = re.search(
        r'^(\s*)"nav\.dashboard"\s*:\s*"[^"]*",\s*$',
        text, re.MULTILINE,
    )
    if anchor_match is None:
        anchor_match = re.search(
            r'^(\s*)"nav\.[\w_]+"\s*:\s*"[^"]*",\s*$',
            text, re.MULTILINE,
        )
    if anchor_match is None:
        print(f"  {code}: no nav.* anchor found, skipping")
        return 0, 0, len(TRANSLATIONS)

    indent = anchor_match.group(1)
    insert_pos = anchor_match.end()
    new_lines = []

    for key, by_locale in TRANSLATIONS.items():
        target = by_locale.get(code)
        if target is None:
            skipped += 1
            continue

        existing = re.search(
            r'("' + re.escape(key) + r'"\s*:\s*")'
            r'((?:[^"\\]|\\.)*)'
            r'(")',
            text,
        )
        if existing:
            escaped = target.replace('\\', '\\\\').replace('"', '\\"')
            new = re.sub(
                r'("' + re.escape(key) + r'"\s*:\s*")'
                r'((?:[^"\\]|\\.)*)'
                r'(")',
                lambda m: m.group(1) + escaped + m.group(3),
                text, count=1,
            )
            text = new
            replaced += 1
        else:
            escaped = target.replace('\\', '\\\\').replace('"', '\\"')
            new_lines.append(f'\n{indent}"{key}": "{escaped}",')
            inserted += 1

    if new_lines:
        text = text[:insert_pos] + ''.join(new_lines) + text[insert_pos:]

    if text != original:
        path.write_text(text, encoding='utf-8')
    return inserted, replaced, skipped


def main():
    locales = ['de', 'fr', 'es', 'it', 'pt', 'ru', 'zh', 'ja', 'ko', 'ar', 'hi',
               'th', 'vi', 'id', 'tr', 'nl', 'pl', 'cs', 'sv', 'no', 'da', 'fi',
               'ro', 'bg', 'hr']
    total_i = total_r = total_s = 0
    print(f"Insert/replace {len(TRANSLATIONS)} keys across {len(locales)} locales...")
    for code in locales:
        i, r, s = patch_locale(code)
        total_i += i
        total_r += r
        total_s += s
        print(f"  {code:5s}: inserted={i:3d}  replaced={r:3d}  skipped={s:3d}")
    print(f"\nTOTAL: {total_i} inserted, {total_r} replaced, {total_s} skipped")


if __name__ == '__main__':
    main()
