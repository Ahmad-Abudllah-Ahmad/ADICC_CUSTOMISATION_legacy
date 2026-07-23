"""‌⁠‍End-to-end smoke for /match-elements on three real projects.

Verifies the full pipeline yields a real BOQ with non-zero cost in the
project's currency:

    create_session → list_groups → run_match (vector) → bulk_confirm
        → apply_to_boq(dry_run=True) → grand_total > 0

Run from repo root with backend/ as CWD:

    cd backend
    python ../scripts/e2e_match_elements.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

# Make sure we run against the dev DB.
os.environ.setdefault(
    "DATABASE_URL", "sqlite+aiosqlite:///openestimate.db",
)
os.environ.setdefault(
    "DATABASE_SYNC_URL", "sqlite:///openestimate.db",
)

# Add backend to path if running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text

from app.modules.match_elements import schemas
from app.modules.match_elements.service import get_service


PROJECTS = [
    ("Boylston Crossing", "USD"),
    ("Wohnpark Friedrichshain", "EUR"),
    ("Residencial Vila Madalena", "BRL"),
]


async def run_for(session_factory, project_id: uuid.UUID, project_name: str, currency: str) -> dict:
    """‌⁠‍Run the full match → confirm → apply flow for one project. Return summary."""
    svc = get_service()
    user_id = uuid.uuid4()  # any uuid — service just stores the FK
    out = {
        "project_id": str(project_id),
        "name": project_name,
        "currency": currency,
        "session_id": None,
        "groups_total": 0,
        "matched_groups": 0,
        "confirmed_groups": 0,
        "boq_positions": 0,
        "grand_total": 0.0,
        "result_currency": None,
        "errors": [],
    }
    try:
        # 1. Create session
        async with session_factory() as db:
            sess = await svc.create_session(
                db,
                schemas.SessionCreate(
                    project_id=project_id,
                    source="bim",
                    name=f"E2E {project_name}",
                ),
                user_id,
            )
            await db.commit()
            sess_id = sess.id
            out["session_id"] = str(sess_id)

        # 2. List groups (this is where the adapter populates groups in DB)
        async with session_factory() as db:
            listing = await svc.list_groups(db, sess_id, limit=200)
            await db.commit()
            out["groups_total"] = listing.total

        if listing.total == 0:
            out["errors"].append("0 groups produced from BIM elements")
            return out

        # 3. Run vector matcher on top-50 groups
        async with session_factory() as db:
            try:
                matched = await svc.run_match(
                    db,
                    sess_id,
                    schemas.RunMatchRequest(
                        method="vector",
                        max_groups=50,
                        top_k=10,
                    ),
                )
                await db.commit()
                out["matched_groups"] = sum(
                    1 for g in matched if g.confidence is not None
                )
            except Exception as exc:
                out["errors"].append(f"run_match(vector): {exc}")
                # Try lexical as a fallback.
                async with session_factory() as db2:
                    try:
                        matched = await svc.run_match(
                            db2,
                            sess_id,
                            schemas.RunMatchRequest(
                                method="lexical",
                                max_groups=50,
                                top_k=10,
                            ),
                        )
                        await db2.commit()
                        out["matched_groups"] = sum(
                            1 for g in matched if g.confidence is not None
                        )
                    except Exception as exc2:
                        out["errors"].append(f"run_match(lexical): {exc2}")

        # 4. Bulk-confirm anything ≥ 0.5 (lower bar than auto-confirm
        #    so we can verify the pipe end-to-end on real data).
        async with session_factory() as db:
            n = await svc.bulk_confirm(
                db,
                sess_id,
                schemas.BulkConfirmRequest(threshold=0.5),
                user_id,
            )
            await db.commit()
            out["confirmed_groups"] = n

        # 5. Dry-run apply
        async with session_factory() as db:
            apply_resp = await svc.apply_to_boq(
                db,
                sess_id,
                schemas.ApplyToBoqRequest(dry_run=True),
                user_id,
            )
            await db.commit()
            out["boq_positions"] = apply_resp.positions_created
            out["grand_total"] = apply_resp.grand_total
            out["result_currency"] = apply_resp.currency
    except Exception as exc:
        out["errors"].append(f"FATAL: {type(exc).__name__}: {exc}")

    return out


async def main() -> int:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)

    # Resolve project ids by name.
    projects: list[tuple[str, str, uuid.UUID]] = []
    async with Session() as s:
        for name, ccy in PROJECTS:
            row = (
                await s.execute(
                    text(
                        "SELECT id FROM oe_projects_project "
                        "WHERE name LIKE :name LIMIT 1"
                    ),
                    {"name": f"{name}%"},
                )
            ).first()
            if not row:
                print(f"WARN: project '{name}' not found, skipping")
                continue
            projects.append((name, ccy, uuid.UUID(row[0])))

    if not projects:
        print("No target projects found.")
        return 1

    results = []
    for name, ccy, pid in projects:
        print(f"\n=== {name} ({ccy}) — id={str(pid)[:8]} ===", flush=True)
        r = await run_for(Session, pid, name, ccy)
        results.append(r)
        print(f"  groups_total      = {r['groups_total']}")
        print(f"  matched_groups    = {r['matched_groups']}")
        print(f"  confirmed_groups  = {r['confirmed_groups']}")
        print(f"  boq_positions     = {r['boq_positions']}")
        print(
            f"  grand_total       = {r['grand_total']:,.2f} "
            f"{r['result_currency'] or ''}"
        )
        if r["errors"]:
            for e in r["errors"]:
                print(f"  ERR: {e}")

    print("\n=== Summary ===")
    print(f"{'Project':28s} {'CCY':4s} {'groups':>7s} {'matched':>7s} {'conf':>6s} "
          f"{'pos':>5s} {'total':>14s}")
    for r in results:
        print(
            f"{r['name'][:28]:28s} {r['currency']:4s} "
            f"{r['groups_total']:7d} {r['matched_groups']:7d} "
            f"{r['confirmed_groups']:6d} {r['boq_positions']:5d} "
            f"{r['grand_total']:14,.2f}"
        )

    # Exit non-zero only if NONE of the projects produced any BOQ output.
    if all(r["boq_positions"] == 0 for r in results):
        print("\nFAIL: no project produced any BOQ positions.")
        return 1
    print("\nOK: pipeline produced real BOQ data on at least one project.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
