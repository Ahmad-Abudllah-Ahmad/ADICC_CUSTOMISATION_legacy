"""‌⁠‍
i18n coverage audit for OpenConstructionERP.

Reads frontend/src/app/locales/*.ts and reports:
  - missing keys (present in en.ts but not in locale)
  - identical values (likely untranslated — equal to EN verbatim)
  - per-locale gap counts and top-20 missing examples
  - v3.0.5 critical-key coverage check (nav.*, modules.dev_guide, support.*)
  - top-20 keys missing across the MOST locales

Audit-only — does NOT modify any locale file.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES_DIR = ROOT / "frontend" / "src" / "app" / "locales"
REPORT_PATH = Path(__file__).resolve().parent / "i18n_coverage_report.txt"

MASTER = "en"

# Heuristic skips for identical-value detection.
ACRONYMS = {
    "CPI", "SPI", "KPI", "BIM", "IFC", "CAD", "BOQ", "HVAC", "MEP",
    "AI", "CV", "RFI", "EAC", "DDC", "DIN", "NRM", "GAEB", "RFP",
    "RFQ", "PO", "CO", "FX", "VAT", "QC", "QA", "ID", "URL", "API",
    "PDF", "CSV", "XML", "JSON", "IT", "OK", "UI", "UX", "EVM",
    "OCR", "BCF", "ESG", "GDPR", "SSO", "JWT", "RBAC", "CRUD",
}
BRANDS = {
    "OpenConstructionERP", "DDC", "GitHub", "Slack", "GitLab",
    "Anthropic", "OpenAI", "Google", "PostgreSQL", "Redis", "MinIO",
    "PyPI", "DataDrivenConstruction", "Excel", "Word", "LinkedIn",
    "Twitter", "X", "Mongolia", "Berlin",
}
KEYBOARD_RE = re.compile(r"^(Ctrl|Cmd|Shift|Alt|Meta)\+\w+(\+\w+)?$", re.IGNORECASE)
FILEEXT_RE = re.compile(r"^\.[a-z0-9]{1,5}$", re.IGNORECASE)
EMOJI_RE = re.compile(
    r"^[\U0001F300-\U0001FAFF\U00002600-\U000027BF✂-➰\U0001F000-\U0001F02F]+$"
)
NUMBER_RE = re.compile(r"^[\d.,%+\-\s]+$")
ALLCAPS_RE = re.compile(r"^[A-Z0-9 ./\-+&]+$")
PLACEHOLDER_ONLY_RE = re.compile(r"^\{\{[^}]+\}\}$")


def parse_locale(path: Path) -> dict[str, str]:
    """‌⁠‍Parse a .ts locale file. Flat keys: '"key": "value",' on one line."""
    text = path.read_text(encoding="utf-8")
    result: dict[str, str] = {}

    # Match: "key": "value",  — allowing escaped quotes in value.
    # Skip lines starting with // (comments) and lines with template braces.
    line_re = re.compile(r'^\s*"((?:[^"\\]|\\.)+)"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,?\s*$')

    for raw_line in text.splitlines():
        if raw_line.lstrip().startswith("//"):
            continue
        m = line_re.match(raw_line)
        if not m:
            continue
        key = unescape_ts(m.group(1))
        val = unescape_ts(m.group(2))
        result[key] = val

    return result


def unescape_ts(s: str) -> str:
    """‌⁠‍Undo TS double-quoted string escapes."""
    return (
        s.replace(r"\\", "\\")
        .replace(r"\"", '"')
        .replace(r"\n", "\n")
        .replace(r"\t", "\t")
    )


def is_legit_identical(en_val: str, _key: str) -> bool:
    """Return True if EN==locale is plausibly correct (skip from 'identical' count)."""
    v = en_val.strip()
    if not v:
        return True
    if v in ACRONYMS or v in BRANDS:
        return True
    if KEYBOARD_RE.match(v):
        return True
    if FILEEXT_RE.match(v):
        return True
    if EMOJI_RE.match(v):
        return True
    if NUMBER_RE.match(v):
        return True
    if PLACEHOLDER_ONLY_RE.match(v):
        return True
    # Single char.
    if len(v) <= 1:
        return True
    # Short ALL-CAPS-ish acronyms (≤6 chars, all caps + numbers).
    if len(v) <= 6 and ALLCAPS_RE.match(v) and any(c.isalpha() for c in v):
        return True
    # Pure URLs.
    if v.startswith(("http://", "https://", "www.")):
        return True
    # Tokens like "C30/37", "BSt 500", "DN200" — short, contains digit.
    if len(v) <= 12 and any(c.isdigit() for c in v) and not any(c == " " for c in v[:3]):
        if re.match(r"^[A-Za-z]+\d+", v) or re.match(r"^\d+[A-Za-z]+", v):
            return True
    return False


def main() -> None:
    en_path = LOCALES_DIR / f"{MASTER}.ts"
    en = parse_locale(en_path)
    en_keys = set(en.keys())

    locales = sorted(p.stem for p in LOCALES_DIR.glob("*.ts") if p.stem != MASTER)

    per_locale: dict[str, dict] = {}
    missing_counter: Counter[str] = Counter()
    identical_counter: Counter[str] = Counter()

    for loc in locales:
        loc_path = LOCALES_DIR / f"{loc}.ts"
        data = parse_locale(loc_path)
        loc_keys = set(data.keys())

        missing = sorted(en_keys - loc_keys)
        for k in missing:
            missing_counter[k] += 1

        identical: list[str] = []
        for k in en_keys & loc_keys:
            en_v = en[k]
            loc_v = data[k]
            if not loc_v.strip():
                continue  # honest-unknown empty string
            if loc_v == en_v and not is_legit_identical(en_v, k):
                identical.append(k)
                identical_counter[k] += 1

        per_locale[loc] = {
            "path": str(loc_path).replace("\\", "/"),
            "missing": missing,
            "identical": sorted(identical),
            "total_keys": len(loc_keys),
        }

    # v3.0.5 critical key set.
    v305_keys = sorted(
        k for k in en_keys
        if k.startswith("support.")
        or k in {"nav.add_module", "nav.request_custom_module", "modules.dev_guide"}
    )

    v305_coverage: dict[str, dict[str, list[str]]] = {}  # key -> {missing|identical}
    for k in v305_keys:
        missing_in = [loc for loc in locales if k in set(per_locale[loc]["missing"])]
        identical_in = [loc for loc in locales if k in set(per_locale[loc]["identical"])]
        if missing_in or identical_in:
            v305_coverage[k] = {"missing": missing_in, "identical": identical_in}

    # Top-20 keys missing in MOST locales.
    top_missing = missing_counter.most_common(50)

    # ---- Write report ----
    lines: list[str] = []
    lines.append("# i18n Coverage Audit Report")
    lines.append(f"Master: {MASTER}.ts — {len(en_keys)} keys")
    lines.append(f"Locales audited: {len(locales)}")
    lines.append("")
    lines.append("## Summary table")
    lines.append("")
    header = f"{'locale':<8} {'missing':>8} {'identical':>10} {'total_keys':>11}  status"
    lines.append(header)
    lines.append("-" * len(header))
    for loc in locales:
        d = per_locale[loc]
        m = len(d["missing"])
        i = len(d["identical"])
        gap = m + i
        if gap < 50:
            status = "GREEN <50"
        elif gap < 200:
            status = "YELLOW <200"
        else:
            status = "RED >=200"
        lines.append(f"{loc:<8} {m:>8} {i:>10} {d['total_keys']:>11}  {status}")
    lines.append("")

    # Per-locale top 20 missing examples.
    lines.append("## Top 20 missing keys per locale")
    lines.append("")
    for loc in locales:
        d = per_locale[loc]
        lines.append(f"### {loc} ({len(d['missing'])} missing, {len(d['identical'])} identical)")
        lines.append(f"path: {d['path']}")
        for k in d["missing"][:20]:
            sample = en[k][:60].replace("\n", " ")
            lines.append(f"  - {k}  :: EN={sample!r}")
        if not d["missing"]:
            lines.append("  (no missing keys)")
        lines.append("")

    # v3.0.5 coverage.
    lines.append("## v3.0.5 critical-key coverage")
    lines.append("")
    if not v305_coverage:
        lines.append("All v3.0.5 keys present and translated in every locale.")
    else:
        for k in v305_keys:
            cov = v305_coverage.get(k)
            if cov is None:
                lines.append(f"- {k}: OK (translated in all 26 locales)")
                continue
            miss = cov["missing"]
            iden = cov["identical"]
            bits = []
            if miss:
                bits.append(f"MISSING in {len(miss)}: {', '.join(miss)}")
            if iden:
                bits.append(f"UNTRANSLATED (==EN) in {len(iden)}: {', '.join(iden)}")
            lines.append(f"- {k}: " + " | ".join(bits))
    lines.append("")

    # Top-20 keys missing in MOST locales.
    lines.append("## Top keys missing in the MOST locales (backfill priority)")
    lines.append("")
    if not top_missing:
        lines.append("(No missing keys — every locale has every key. "
                     "Backfill priority comes from the identical-value list below.)")
    for k, count in top_missing[:30]:
        sample = en.get(k, "")[:80].replace("\n", " ")
        lines.append(f"- [{count}/{len(locales)} locales] {k}  :: EN={sample!r}")
    lines.append("")

    # Top-30 keys identical-to-EN in the MOST locales (real backfill priority).
    lines.append("## Top keys identical-to-EN across the MOST locales (real backfill priority)")
    lines.append("")
    for k, count in identical_counter.most_common(30):
        sample = en.get(k, "")[:80].replace("\n", " ")
        lines.append(f"- [{count}/{len(locales)} locales identical] {k}  :: EN={sample!r}")
    lines.append("")

    # Identical-values sample for each locale.
    lines.append("## Identical-values samples (top 10 per locale)")
    lines.append("")
    for loc in locales:
        d = per_locale[loc]
        lines.append(f"### {loc} — {len(d['identical'])} identical-to-EN values")
        for k in d["identical"][:10]:
            sample = en[k][:60].replace("\n", " ")
            lines.append(f"  - {k}  :: {sample!r}")
        if not d["identical"]:
            lines.append("  (none)")
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written: {REPORT_PATH}")
    print(f"EN master keys: {len(en_keys)}")
    print(f"Locales audited: {len(locales)}")
    print()
    print(f"{'locale':<8} {'missing':>8} {'identical':>10}")
    for loc in locales:
        d = per_locale[loc]
        print(f"{loc:<8} {len(d['missing']):>8} {len(d['identical']):>10}")


if __name__ == "__main__":
    main()
