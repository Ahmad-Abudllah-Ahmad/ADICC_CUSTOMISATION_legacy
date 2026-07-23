"""‌⁠‍End-to-end smoke test for the cost database import templates.

Verifies that:
  1. The flat CSV template (`example_us_construction.csv`) uploads via
     `POST /api/v1/costs/import/file/` and all rows land in `oe_costs_item`.
  2. The resource-based recipe JSON (`cost_database_with_assemblies.json`)
     uploads via `POST /api/v1/costs/items` with `components[]` preserved.
  3. Every uploaded code round-trips through `GET /api/v1/costs/items/?q=...`
     with matching unit + rate (within 0.01).
  4. A recipe's `components` array survives the round-trip with the right
     leaf codes and factors.

Usage: python scripts/test_cost_import.py

Requires the backend to be running on http://localhost:8000 with the demo
account seeded (`demo@openconstructionerp.com`).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import requests

API = "http://localhost:8000/api/v1"
DEMO_EMAIL = "demo@openconstructionerp.com"
TEMPLATES = Path(__file__).resolve().parents[1] / "data" / "templates"
CSV_PATH = TEMPLATES / "example_us_construction.csv"
JSON_PATH = TEMPLATES / "cost_database_with_assemblies.json"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def login() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/users/auth/demo-login", json={"email": DEMO_EMAIL}, timeout=30)
    if r.status_code != 200:
        fail(f"login HTTP {r.status_code}: {r.text[:200]}")
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


def import_csv(s: requests.Session) -> int:
    print(f"[1/4] uploading {CSV_PATH.name} via /costs/import/file/")
    with CSV_PATH.open("rb") as fh:
        r = s.post(
            f"{API}/costs/import/file/",
            files={"file": (CSV_PATH.name, fh, "text/csv")},
            timeout=120,
        )
    if r.status_code != 200:
        fail(f"flat CSV import HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    imported = int(data.get("imported", 0))
    skipped = int(data.get("skipped", 0))
    # Idempotency: a re-run after the rows already exist returns
    # imported=0 with skipped > 0 — that's still a pass.
    print(f"      imported={imported}, skipped={skipped}, errors={len(data.get('errors') or [])}")
    return imported + skipped


def push_recipes(s: requests.Session) -> int:
    print(f"[2/4] pushing recipes from {JSON_PATH.name}")
    items = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    created = 0
    already = 0
    for item in items:
        # Idempotent push: 201 on first run, 409 "already exists" on re-run.
        # We treat both as accepted — stage 4 verifies the persisted state.
        r = s.post(f"{API}/costs/", json=item, timeout=180)
        if r.status_code == 201:
            created += 1
            continue
        if r.status_code in (400, 409, 422) and any(
            kw in r.text.lower() for kw in ("exists", "unique", "duplicate")
        ):
            already += 1
            continue
        fail(f"recipe {item['code']} HTTP {r.status_code}: {r.text[:300]}")
    print(f"      recipes: {created} created, {already} already present")
    return created + already


def verify_round_trip(s: requests.Session) -> None:
    print("[3/4] round-tripping all uploaded codes")

    # Pull expected rows from the CSV
    with CSV_PATH.open(encoding="utf-8") as fh:
        expected = list(csv.DictReader(fh))

    missing: list[str] = []
    mismatched: list[str] = []
    for row in expected:
        code = row["code"]
        r = s.get(f"{API}/costs/?q={code}&limit=5", timeout=30)
        if r.status_code != 200:
            missing.append(f"{code}: HTTP {r.status_code}")
            continue
        items = [
            it for it in r.json().get("items", [])
            if it.get("code") == code
        ]
        if not items:
            missing.append(code)
            continue
        got = items[0]
        if got["unit"] != row["unit"]:
            mismatched.append(f"{code}: unit {got['unit']} != {row['unit']}")
        # rate is stored as string-coerced float; compare with epsilon
        if abs(float(got["rate"]) - float(row["rate"])) > 0.01:
            mismatched.append(f"{code}: rate {got['rate']} != {row['rate']}")

    if missing:
        fail(f"missing codes after import ({len(missing)}): {missing[:5]}")
    if mismatched:
        fail(f"mismatched fields ({len(mismatched)}): {mismatched[:5]}")
    print(f"      all {len(expected)} flat rows round-trip cleanly")


def verify_recipe_components(s: requests.Session) -> None:
    print("[4/4] verifying recipe components survive")
    recipes = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    for rec in recipes:
        r = s.get(f"{API}/costs/?q={rec['code']}&limit=5", timeout=30)
        if r.status_code != 200:
            fail(f"recipe lookup {rec['code']}: HTTP {r.status_code}")
        items = [
            it for it in r.json().get("items", [])
            if it.get("code") == rec["code"]
        ]
        if not items:
            fail(f"recipe {rec['code']} not found after push")
        got = items[0]
        got_components = got.get("components") or []
        if len(got_components) != len(rec["components"]):
            fail(
                f"recipe {rec['code']} components count "
                f"{len(got_components)} != {len(rec['components'])}"
            )
        # Compare each by code + factor
        by_code = {c["code"]: c for c in got_components if isinstance(c, dict) and c.get("code")}
        for expected_c in rec["components"]:
            ec_code = expected_c["code"]
            if ec_code not in by_code:
                fail(f"recipe {rec['code']} missing component {ec_code}")
            got_factor = float(by_code[ec_code].get("factor", 0))
            if abs(got_factor - float(expected_c["factor"])) > 1e-6:
                fail(
                    f"recipe {rec['code']} component {ec_code}: "
                    f"factor {got_factor} != {expected_c['factor']}"
                )
    print(f"      all {len(recipes)} recipes have correct component breakdowns")


def main() -> None:
    print(f"== cost-database import smoke test ==")
    print(f"   API: {API}")
    print(f"   CSV: {CSV_PATH}")
    print(f"   JSON: {JSON_PATH}")
    if not CSV_PATH.exists() or not JSON_PATH.exists():
        fail("templates missing — run from repo root")
    s = login()
    n_csv = import_csv(s)
    n_rec = push_recipes(s)
    verify_round_trip(s)
    verify_recipe_components(s)
    print()
    print(f"PASS — {n_csv} leaves + {n_rec} recipes imported and verified end-to-end")


if __name__ == "__main__":
    main()
