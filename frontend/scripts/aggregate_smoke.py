#!/usr/bin/env python3
"""Aggregate qa-smoke/<engine>/<slug>.json findings into a triage report.

Run from frontend/ after a smoke sweep:  python scripts/aggregate_smoke.py
Prints crashes, auth losses, nav errors, leaked i18n keys, and noisy console/
network routes, grouped so the worst issues surface first.
"""
import glob
import json
import os
import sys

BASE = os.environ.get("OE_SMOKE_DIR", "qa-smoke")
ENGINES = ["chromium", "firefox", "webkit"]


def load():
    routes = {}
    for e in ENGINES:
        for f in glob.glob(os.path.join(BASE, e, "*.json")):
            try:
                d = json.load(open(f, encoding="utf-8"))
            except Exception as ex:  # noqa: BLE001
                print(f"  (skip unreadable {f}: {ex})")
                continue
            routes.setdefault(d.get("slug", os.path.basename(f)), {})[e] = d
    return routes


def main():
    routes = load()
    total = sum(len(v) for v in routes.values())
    print(f"== smoke aggregate: {len(routes)} routes, {total} (route x engine) results ==\n")

    crashes, logins, navs, keys, nets, consoles = [], [], [], [], [], []
    for slug, per in sorted(routes.items()):
        for e, d in per.items():
            if d.get("crashed"):
                crashes.append((slug, e, " ".join(d.get("crashes", []))[:160]))
            if d.get("redirectedToLogin"):
                logins.append((slug, e))
            if d.get("navError"):
                navs.append((slug, e, d["navError"][:120]))
            if d.get("suspectedKeys"):
                keys.append((slug, e, d["suspectedKeys"]))
            if d.get("netErrors"):
                nets.append((slug, e, d["netErrors"][:4]))
            if d.get("consoleErrorCount", 0) > 3:
                consoles.append((slug, e, d["consoleErrorCount"]))

    def section(title, rows, fmt):
        print(f"--- {title}: {len(rows)} ---")
        for r in rows:
            print("  " + fmt(r))
        print()

    section("CRASHES (React ErrorBoundary / pageerror)", crashes, lambda r: f"{r[0]} [{r[1]}] {r[2]}")
    section("AUTH LOST (redirected to /login)", logins, lambda r: f"{r[0]} [{r[1]}]")
    section("NAV ERRORS (goto failed/timeout)", navs, lambda r: f"{r[0]} [{r[1]}] {r[2]}")
    section("SUSPECTED UNTRANSLATED KEYS", keys, lambda r: f"{r[0]} [{r[1]}] {r[2]}")
    section("API ERRORS (>=400 on /api during load)", nets, lambda r: f"{r[0]} [{r[1]}] {r[2]}")
    section("NOISY CONSOLE (>3 errors)", consoles, lambda r: f"{r[0]} [{r[1]}] {r[2]} errors")

    blockers = len(crashes) + len(logins)
    print(f"== BLOCKERS (crashes+auth): {blockers} | nav:{len(navs)} keys:{len(keys)} api:{len(nets)} console:{len(consoles)} ==")
    return 0 if blockers == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
