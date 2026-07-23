"""‌⁠‍Find identical-to-EN keys per locale, scoped to the most-visible namespaces."""
import re
import json
from pathlib import Path

PAIR = re.compile(r'"((?:[^"\\]|\\.)+)"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)
ROOT = Path(__file__).resolve().parents[1]

# Namespaces visible on every page or top-level nav (priority backfill)
VISIBLE = (
    'nav.',
    'sidebar.',
    'header.',
    'dashboard.',
    'modules.',
    'onboarding.',
    'language.',
    'common.',
    'footer.',
    'topbar.',
    'app.',
)

# Exclude keys whose value is inherently locale-neutral
NEUTRAL_KEY_PATTERNS = (
    re.compile(r'\.export_format_'),
    re.compile(r'\.shortcut_'),
    re.compile(r'\.regex_'),
    re.compile(r'\.file_extension_'),
)
NEUTRAL_VALUE = re.compile(
    r'^(CSV|XML|JSON|GAEB|PDF|XLSX|XLS|DOCX|DWG|DXF|RVT|IFC|BCF|API|UI|UX|'
    r'BIM|CAD|HVAC|MEP|BOQ|CWICR|RFI|EAC|CPI|SPI|KPI|AI|CV|ESG|QMS|HSE|'
    r'BI|CRM|ERP|ROI|MVP|CTA|FAQ|TBD|TODO|N/A|NA)( |$)'
)


def parse_ts(path):
    text = Path(path).read_text(encoding='utf-8')
    return dict(PAIR.findall(text))


def is_neutral(key, value):
    if any(p.search(key) for p in NEUTRAL_KEY_PATTERNS):
        return True
    if len(value) <= 2:
        return True
    if NEUTRAL_VALUE.match(value):
        return True
    # Numbers / punctuation only
    if re.match(r'^[\d\s\.,;:!\-_/\\(){}\[\]<>+=*&%$#@?]+$', value):
        return True
    # Pure placeholders {{x}} or templates with no English words
    if re.match(r'^[\s{}\d\-_/(),:.+%a-z]+$', value) and not re.search(r'[A-Z]', value):
        return True
    return False


def main():
    en = parse_ts(ROOT / 'frontend/src/app/locales/en.ts')

    visible_keys = {
        k: v for k, v in en.items()
        if any(k.startswith(p) for p in VISIBLE)
    }
    actionable = {k: v for k, v in visible_keys.items() if not is_neutral(k, v)}
    print(f"en.ts total: {len(en)}")
    print(f"visible-namespace keys: {len(visible_keys)} (actionable: {len(actionable)})")
    print(f"  filtered out as neutral: {len(visible_keys) - len(actionable)}")

    locales = ['de', 'fr', 'es', 'it', 'pt', 'ru', 'zh', 'ja', 'ko', 'ar', 'hi',
               'th', 'vi', 'id', 'tr', 'nl', 'pl', 'cs', 'sv', 'no', 'da', 'fi',
               'ro', 'bg', 'hr', 'mn']

    rows = []
    per_locale_keys = {}
    key_to_locales = {}

    for code in locales:
        d = parse_ts(ROOT / f'frontend/src/app/locales/{code}.ts')
        identical = [k for k, v in actionable.items() if d.get(k) == v]
        rows.append((code, len(identical)))
        per_locale_keys[code] = identical
        for k in identical:
            key_to_locales.setdefault(k, []).append(code)

    rows.sort(key=lambda x: -x[1])
    print("\nLocale | identical visible-namespace keys (untranslated, actionable)")
    for c, n in rows:
        flag = 'RED ' if n > 100 else ('YEL ' if n > 30 else 'GRN ')
        print(f"  {c:5s} | {n:4d}  {flag}")

    print("\nTop 30 visible keys identical in MOST locales:")
    for k, codes in sorted(key_to_locales.items(), key=lambda x: -len(x[1]))[:30]:
        print(f"  [{len(codes):2d}/26] {k} = {actionable[k]!r}")

    out = ROOT / 'scripts/_visible_gap.json'
    out.write_text(json.dumps({
        'visible_keys': actionable,
        'per_locale_keys': per_locale_keys,
        'key_to_locales': key_to_locales,
        'summary': rows,
    }, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"\nDumped to {out}")


if __name__ == '__main__':
    main()
