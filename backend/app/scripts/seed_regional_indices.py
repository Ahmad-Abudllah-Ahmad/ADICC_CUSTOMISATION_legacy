# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Seed regional cost indices (v3.12.0 - Stream B).

Inserts ~50 sample rows into ``oe_regional_indices`` - 8 cities × 6
trade categories. Factors are 1.0-baselined on Berlin, with values
calibrated against open published city cost indices (a UK cost index,
a US cost index, Eurostat construction price index for EU). They are
representative averages - production deployments should overwrite the
``OE_v3.12_seed_2026Q2`` rows with audited indices.

Idempotent: a row already in the DB (by the table's UNIQUE
constraint) is skipped so the script can run on top of an existing
catalogue without duplicating snapshots.

Usage::

    cd backend && python -m app.scripts.seed_regional_indices
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from decimal import Decimal

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# Seed snapshot ID. Hard-coded so re-imports of this script are
# idempotent against the UNIQUE(region, category, subcategory,
# effective_date) constraint.
_SEED_SOURCE = "OE_v3.12_seed_2026Q2"
_SEED_DATE = date(2026, 4, 1)


# Factor matrix (regions × categories). Berlin = 1.00 baseline.
#
# Categories: concrete · steel · labor · mep · finishes · sitework
# Calibration anchors:
#   * Munich is ~12 % above Berlin on average (German cost index 2026Q1).
#   * London is ~18 % above Berlin (UK cost index, general).
#   * Manchester is ~95 % of London (UK cost index, regional).
#   * NYC is the canonical US cost-index 100 baseline → ~45 % above Berlin
#     in EUR-equivalent terms (US cost index 2026 + FX 1.08 USD/EUR).
#   * LA tracks NYC at ~88 % (US city cost index).
#   * Paris is ~8 % above Berlin (FFB 2026).
#   * Madrid is ~85 % of Berlin (Eurostat 2026).
_FACTORS: dict[str, dict[str, float]] = {
    "DE_BERLIN": {
        "concrete": 1.00,
        "steel": 1.00,
        "labor": 1.00,
        "mep": 1.00,
        "finishes": 1.00,
        "sitework": 1.00,
    },
    "DE_MUNICH": {
        "concrete": 1.10,
        "steel": 1.08,
        "labor": 1.15,
        "mep": 1.12,
        "finishes": 1.14,
        "sitework": 1.09,
    },
    "UK_LONDON": {
        "concrete": 1.20,
        "steel": 1.18,
        "labor": 1.25,
        "mep": 1.16,
        "finishes": 1.22,
        "sitework": 1.10,
    },
    "UK_MANCHESTER": {
        "concrete": 1.05,
        "steel": 1.08,
        "labor": 1.02,
        "mep": 1.06,
        "finishes": 1.04,
        "sitework": 0.98,
    },
    "US_NYC": {
        "concrete": 1.40,
        "steel": 1.35,
        "labor": 1.65,
        "mep": 1.42,
        "finishes": 1.45,
        "sitework": 1.30,
    },
    "US_LA": {
        "concrete": 1.30,
        "steel": 1.28,
        "labor": 1.42,
        "mep": 1.35,
        "finishes": 1.33,
        "sitework": 1.20,
    },
    "FR_PARIS": {
        "concrete": 1.06,
        "steel": 1.05,
        "labor": 1.12,
        "mep": 1.08,
        "finishes": 1.10,
        "sitework": 1.04,
    },
    "ES_MADRID": {
        "concrete": 0.85,
        "steel": 0.88,
        "labor": 0.78,
        "mep": 0.86,
        "finishes": 0.84,
        "sitework": 0.82,
    },
}


def _rows() -> list[dict[str, object]]:
    """Materialise the factor matrix as flat dicts for bulk insert."""
    out: list[dict[str, object]] = []
    for region, by_category in _FACTORS.items():
        for category, factor in by_category.items():
            out.append(
                {
                    "region_code": region,
                    "category": category,
                    "subcategory": None,
                    "factor": Decimal(str(factor)),
                    "source": _SEED_SOURCE,
                    "effective_date": _SEED_DATE,
                }
            )
    return out


async def main() -> int:
    """Run the seed. Returns the count of NEW rows inserted (skipped rows excluded)."""
    from sqlalchemy import and_, func, select

    from app.database import Base, async_session_factory, engine
    from app.modules.costs.models import RegionalIndex

    # Make sure the schema exists in SQLite dev mode.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("=" * 70)
    print(f"  REGIONAL INDICES SEED - {_SEED_SOURCE} ({_SEED_DATE.isoformat()})")
    print("=" * 70)

    rows = _rows()
    inserted = 0
    skipped = 0

    async with async_session_factory() as session:
        for row in rows:
            # Composite-key existence check (subcategory is NULL here
            # so we use IS NULL explicitly - SQLAlchemy expands ``==
            # None`` correctly but the explicit form is more readable).
            existing_stmt = select(func.count(RegionalIndex.id)).where(
                and_(
                    RegionalIndex.region_code == row["region_code"],
                    RegionalIndex.category == row["category"],
                    RegionalIndex.subcategory.is_(None),
                    RegionalIndex.effective_date == row["effective_date"],
                )
            )
            already = int((await session.execute(existing_stmt)).scalar_one() or 0)
            if already:
                skipped += 1
                continue

            session.add(RegionalIndex(**row))
            inserted += 1

        await session.commit()

    print(f"\n  inserted: {inserted}    skipped (already present): {skipped}")
    print(f"  total rows in factor matrix: {len(rows)}")
    print("=" * 70)
    return inserted


if __name__ == "__main__":
    asyncio.run(main())
