"""
Stealth watermark injector / verifier for OpenConstructionERP.

Adds Layer-3 authorship fingerprints on top of the visible+stealth markers
documented in internal identity-marker notes. The point: even if a
fork strips every Layer-1/2 watermark, hundreds of Layer-3 zero-width
fingerprints survive in code that still reads identically to a human.

PEPPER  = U+200C  ZERO WIDTH NON-JOINER
        + U+2060  WORD JOINER
        + U+200D  ZERO WIDTH JOINER
A 3-codepoint sequence that is **invisible** in editors, terminals, and
rendered HTML, but is preserved verbatim by Python source, TypeScript
source, Vite/esbuild bundling, Ruff/Prettier formatting, and `git diff`.
The combination ZWNJ + WJ + ZWJ is exceptionally uncommon -- searching
GitHub for any single literal occurrence of it returns essentially zero
hits, so mass-presence in a fork is statistically conclusive evidence.

INJECTION SLOTS -- chosen for survivability + low risk:
  * Python triple-quoted docstrings   (right after the opening triple-quote)
  * TypeScript defaultValue: '...'    (right before the closing quote)
  * TypeScript defaultValue: "..."    (right before the closing quote)
These slots:
  - Are NOT compared by `==` in tests (defaultValue is i18n fallback;
    docstrings are only read by tooling that strips whitespace anyway).
  - Are preserved by every modern formatter (verified: Ruff, Prettier).
  - Are not parsed as JSON / YAML / TOML.

USAGE
  python tools/watermark/stealth_watermarks.py inject   # inject + write registry
  python tools/watermark/stealth_watermarks.py verify   # confirm registry intact
  python tools/watermark/stealth_watermarks.py count    # just count current pepper occurrences

The registry (tools/watermark/registry.json) is committed to the repo;
it lists every injection site so Artem can prove which lines carry the
fingerprint. The pepper itself is also recoverable from any fork by
simply grepping for the 3-codepoint sequence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

PEPPER = "‌⁠‍"
PEPPER_HEX = PEPPER.encode("utf-8").hex()

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = Path(__file__).parent / "registry.json"

EXCLUDE_DIRS = {
    "node_modules",
    "dist",
    "build",
    "_frontend_dist",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "egg-info",
    "tests",  # avoid string-equality failures in test assertions
    "__tests__",
    "fixtures",
    "login-variants",  # standalone HTML mockups
    "alembic",  # migrations -- versioned by hash, leave alone
    "migrations",
    "tools",  # don't watermark the watermark tool itself
}

EXCLUDE_FILE_SUFFIXES = {
    ".min.js",
    ".min.css",
    ".lock",
    ".log",
}

# Exact repo-relative path prefixes to skip. Unlike EXCLUDE_DIRS (which
# matches a directory basename anywhere in the tree), these target one
# specific subtree only. `backend/app/modules/clash` is excluded because
# it is being authored concurrently by another worktree — watermarking it
# here would race that work. The frontend `clash` feature is unaffected.
EXCLUDE_PATH_PREFIXES = (
    "backend/app/modules/clash",
)

PY_DOCSTRING_RE = re.compile(
    r'(?P<open>""")(?!""")(?P<body>(?:[^"\\]|\\.|"(?!"")|"")*?)(?P<close>""")',
    re.DOTALL,
)

TS_DEFAULT_VALUE_RE = re.compile(
    r"defaultValue:\s*(?P<quote>['\"])(?P<body>(?:[^\\\n]|\\.)*?)(?P=quote)"
)


@dataclass
class Mark:
    """A single watermark injection site."""

    file: str  # path relative to repo root
    line: int  # 1-based line number where the literal starts
    kind: str  # "py-docstring" | "ts-defaultvalue"
    sha256: str  # sha256 of the original literal (without pepper) -- proof anchor


def is_excluded(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDE_DIRS:
        return True
    rel_posix = path.as_posix()
    for prefix in EXCLUDE_PATH_PREFIXES:
        if rel_posix == prefix or rel_posix.startswith(prefix + "/"):
            return True
    for suf in EXCLUDE_FILE_SUFFIXES:
        if path.name.endswith(suf):
            return True
    return False


def walk_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in suffixes:
            continue
        rel = p.relative_to(root)
        if is_excluded(rel):
            continue
        out.append(p)
    return out


def inject_python(path: Path, max_per_file: int = 3) -> list[Mark]:
    """
    Insert the pepper directly after the opening triple-quote of up to
    `max_per_file` docstrings in the file. Skips literals that already
    contain the pepper (idempotent).
    """
    src = path.read_text(encoding="utf-8")
    if PEPPER in src:
        # File already watermarked -- still report any existing marks
        marks: list[Mark] = []
        for m in PY_DOCSTRING_RE.finditer(src):
            if PEPPER in m.group("body"):
                line = src[: m.start()].count("\n") + 1
                body_no_pepper = m.group("body").replace(PEPPER, "")
                marks.append(
                    Mark(
                        file=str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                        line=line,
                        kind="py-docstring",
                        sha256=hashlib.sha256(body_no_pepper.encode("utf-8")).hexdigest()[:16],
                    )
                )
        return marks

    marks: list[Mark] = []
    new_src_parts: list[str] = []
    last = 0
    injected = 0
    for m in PY_DOCSTRING_RE.finditer(src):
        if injected >= max_per_file:
            break
        body = m.group("body")
        # Skip empty docstrings and one-liners shorter than 8 chars
        if len(body.strip()) < 8:
            continue
        # Skip docstrings that already carry pepper (defensive)
        if PEPPER in body:
            continue
        line = src[: m.start()].count("\n") + 1
        # Insert pepper directly after the opening triple-quote
        new_src_parts.append(src[last : m.start("body")])
        new_src_parts.append(PEPPER)
        new_src_parts.append(body)
        last = m.end("body")
        marks.append(
            Mark(
                file=str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                line=line,
                kind="py-docstring",
                sha256=hashlib.sha256(body.encode("utf-8")).hexdigest()[:16],
            )
        )
        injected += 1
    if not marks:
        return []
    new_src_parts.append(src[last:])
    new_src = "".join(new_src_parts)
    path.write_text(new_src, encoding="utf-8", newline="\n")
    return marks


def inject_typescript(path: Path, max_per_file: int = 5) -> list[Mark]:
    """
    Insert the pepper just before the closing quote of up to
    `max_per_file` `defaultValue: '...'` strings. Idempotent.
    """
    src = path.read_text(encoding="utf-8")
    if PEPPER in src:
        marks: list[Mark] = []
        for m in TS_DEFAULT_VALUE_RE.finditer(src):
            if PEPPER in m.group("body"):
                line = src[: m.start()].count("\n") + 1
                body_no_pepper = m.group("body").replace(PEPPER, "")
                marks.append(
                    Mark(
                        file=str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                        line=line,
                        kind="ts-defaultvalue",
                        sha256=hashlib.sha256(body_no_pepper.encode("utf-8")).hexdigest()[:16],
                    )
                )
        return marks

    marks: list[Mark] = []
    new_src_parts: list[str] = []
    last = 0
    injected = 0
    for m in TS_DEFAULT_VALUE_RE.finditer(src):
        if injected >= max_per_file:
            break
        body = m.group("body")
        # Skip very short fallback strings to avoid disrupting i18n keys
        if len(body) < 6:
            continue
        if PEPPER in body:
            continue
        line = src[: m.start()].count("\n") + 1
        # Insert pepper just before the closing quote
        new_src_parts.append(src[last : m.end("body")])
        new_src_parts.append(PEPPER)
        last = m.end("body")
        marks.append(
            Mark(
                file=str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                line=line,
                kind="ts-defaultvalue",
                sha256=hashlib.sha256(body.encode("utf-8")).hexdigest()[:16],
            )
        )
        injected += 1
    if not marks:
        return []
    new_src_parts.append(src[last:])
    new_src = "".join(new_src_parts)
    path.write_text(new_src, encoding="utf-8", newline="\n")
    return marks


def cmd_inject() -> None:
    py_files = walk_files(REPO_ROOT, (".py",))
    ts_files = walk_files(REPO_ROOT, (".ts", ".tsx"))
    print(f"Scanning {len(py_files)} .py + {len(ts_files)} .ts/.tsx files…")

    all_marks: list[Mark] = []
    py_files_marked = 0
    ts_files_marked = 0

    for p in py_files:
        try:
            marks = inject_python(p)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {p}: {e}")
            continue
        if marks:
            all_marks.extend(marks)
            py_files_marked += 1

    for p in ts_files:
        try:
            marks = inject_typescript(p)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {p}: {e}")
            continue
        if marks:
            all_marks.extend(marks)
            ts_files_marked += 1

    registry = {
        "pepper_hex": PEPPER_HEX,
        "pepper_codepoints": [hex(ord(c)) for c in PEPPER],
        "pepper_description": "ZWNJ + WJ + ZWJ -- invisible 3-codepoint authorship fingerprint",
        "owner": "OpenConstructionERP / DataDrivenConstruction · Artem Boiko",
        "license": "AGPL-3.0-or-later",
        "excluded_path_prefixes": list(EXCLUDE_PATH_PREFIXES),
        "total_marks": len(all_marks),
        "py_files_marked": py_files_marked,
        "ts_files_marked": ts_files_marked,
        "marks": [asdict(m) for m in all_marks],
    }
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"Injected {len(all_marks)} marks "
        f"({py_files_marked} .py + {ts_files_marked} .ts/.tsx files). "
        f"Registry -> {REGISTRY_PATH.relative_to(REPO_ROOT)}"
    )


def cmd_verify() -> None:
    if not REGISTRY_PATH.exists():
        print(f"No registry at {REGISTRY_PATH} -- run `inject` first.")
        sys.exit(2)
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    expected = registry["marks"]
    missing: list[dict] = []
    intact = 0
    for entry in expected:
        path = REPO_ROOT / entry["file"]
        if not path.exists():
            missing.append({**entry, "reason": "file-deleted"})
            continue
        src = path.read_text(encoding="utf-8")
        if PEPPER not in src:
            missing.append({**entry, "reason": "pepper-stripped"})
            continue
        # Find the matching literal by sha256 of pepper-stripped body
        if entry["kind"] == "py-docstring":
            found = False
            for m in PY_DOCSTRING_RE.finditer(src):
                body = m.group("body").replace(PEPPER, "")
                if hashlib.sha256(body.encode("utf-8")).hexdigest()[:16] == entry["sha256"]:
                    if PEPPER in m.group("body"):
                        found = True
                        break
            if not found:
                missing.append({**entry, "reason": "literal-changed-or-pepper-removed"})
                continue
        elif entry["kind"] == "ts-defaultvalue":
            found = False
            for m in TS_DEFAULT_VALUE_RE.finditer(src):
                body = m.group("body").replace(PEPPER, "")
                if hashlib.sha256(body.encode("utf-8")).hexdigest()[:16] == entry["sha256"]:
                    if PEPPER in m.group("body"):
                        found = True
                        break
            if not found:
                missing.append({**entry, "reason": "literal-changed-or-pepper-removed"})
                continue
        intact += 1

    total = len(expected)
    print(f"{intact}/{total} marks intact, {len(missing)} missing.")
    if missing:
        print("\nFirst 10 missing:")
        for m in missing[:10]:
            print(f"  {m['file']}:{m['line']} ({m['kind']}) -- {m['reason']}")
        sys.exit(1)


def cmd_count() -> None:
    """
    Standalone scan -- no registry needed. Walks the repo and counts every
    pepper occurrence. Useful against a suspected fork: clone the fork,
    `python tools/watermark/stealth_watermarks.py count`, observe whether
    the count matches our registry total.
    """
    total = 0
    files_with_pepper = 0
    for suf in (".py", ".ts", ".tsx"):
        for p in REPO_ROOT.rglob(f"*{suf}"):
            if not p.is_file():
                continue
            rel = p.relative_to(REPO_ROOT)
            if is_excluded(rel):
                continue
            try:
                src = p.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                continue
            n = src.count(PEPPER)
            if n > 0:
                total += n
                files_with_pepper += 1
    print(f"Pepper occurrences: {total} across {files_with_pepper} files")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stealth watermark tool")
    parser.add_argument("cmd", choices=["inject", "verify", "count"])
    args = parser.parse_args()
    {"inject": cmd_inject, "verify": cmd_verify, "count": cmd_count}[args.cmd]()


if __name__ == "__main__":
    main()
