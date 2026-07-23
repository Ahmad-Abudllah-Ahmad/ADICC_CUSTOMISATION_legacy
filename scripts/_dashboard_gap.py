"""‌⁠‍Quick gap analysis for dashboard.* keys per locale."""
import re
import json
from pathlib import Path

PAIR = re.compile(r'"((?:[^"\\]|\\.)+)"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)
ROOT = Path(__file__).resolve().parents[1]


def parse_ts(path):
    text = Path(path).read_text(encoding='utf-8')
    return dict(PAIR.findall(text))


def main():
    en = parse_ts(ROOT / 'frontend/src/app/locales/en.ts')
    dashboard_keys = {k: v for k, v in en.items() if k.startswith('dashboard.')}
    print(f"en.ts total: {len(en)}  | dashboard.*: {len(dashboard_keys)}")

    locales = ['de', 'fr', 'es', 'it', 'pt', 'ru', 'zh', 'ja', 'ko', 'ar', 'hi',
               'th', 'vi', 'id', 'tr', 'nl', 'pl', 'cs', 'sv', 'no', 'da', 'fi',
               'ro', 'bg', 'hr', 'mn']

    summary = []
    missing_by_key = {}
    identical_by_key = {}
    per_locale_missing = {}

    for code in locales:
        d = parse_ts(ROOT / f'frontend/src/app/locales/{code}.ts')
        missing = [k for k in dashboard_keys if k not in d]
        identical = [k for k, v in dashboard_keys.items()
                     if k in d and d[k] == v and len(v) > 3]
        summary.append((code, len(missing), len(identical)))
        per_locale_missing[code] = missing
        for k in missing:
            missing_by_key.setdefault(k, []).append(code)
        for k in identical:
            identical_by_key.setdefault(k, []).append(code)

    print("\nLocale | missing | identical-to-EN")
    for c, m, i in summary:
        flag = "RED" if (m + i) > 30 else ("YEL" if (m + i) > 5 else "GRN")
        print(f"  {c:5s} | {m:7d} | {i:6d}  {flag}")

    print("\nTop missing keys across locales:")
    for k, codes in sorted(missing_by_key.items(), key=lambda x: -len(x[1])):
        print(f"  [{len(codes):2d}/26] {k} = {dashboard_keys[k]!r}")

    print("\nTop identical-to-EN keys:")
    for k, codes in sorted(identical_by_key.items(), key=lambda x: -len(x[1])):
        print(f"  [{len(codes):2d}/26] {k} = {dashboard_keys[k]!r}")

    # Dump for downstream
    out = ROOT / 'scripts/_dashboard_gap_report.json'
    out.write_text(json.dumps({
        'dashboard_keys': dashboard_keys,
        'summary': summary,
        'missing_by_key': missing_by_key,
        'identical_by_key': identical_by_key,
        'per_locale_missing': per_locale_missing,
    }, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"\nDumped to {out}")


if __name__ == '__main__':
    main()
