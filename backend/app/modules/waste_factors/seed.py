# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Default waste-factor library seed.

Loads a small set of generic starter multipliers (concrete, rebar, tiling,
blockwork, and a few more common trades) so the factor library is useful out of
the box. Values are deliberately conservative, generic starting points an
estimator is expected to tune per project and region; they name no supplier or
product, only the material / work category.

Module import stays light on purpose: only :data:`DEFAULT_WASTE_FACTORS` and
stdlib live at module top, and the ORM / session imports are deferred inside
:func:`seed_waste_factors`, so the pure default data can be imported (and
unit-tested) without a database or SQLAlchemy on the path.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# category, label, factor (>= 1, gross = net * factor), note.
DEFAULT_WASTE_FACTORS: list[dict[str, object]] = [
    {
        "category": "concrete",
        "label": "Concrete (over-pour + spillage)",
        "factor": Decimal("1.03"),
        "note": "Allowance for over-pour, spillage and surface irregularity.",
    },
    {
        "category": "rebar",
        "label": "Reinforcement bar (laps + offcuts)",
        "factor": Decimal("1.10"),
        "note": "Covers lap lengths and bar offcuts beyond the net scheduled steel.",
    },
    {
        "category": "tiling",
        "label": "Tiling (cuts + breakage)",
        "factor": Decimal("1.10"),
        "note": "Edge cuts and breakage on wall and floor tiling.",
    },
    {
        "category": "blockwork",
        "label": "Blockwork (breakage + cuts)",
        "factor": Decimal("1.05"),
        "note": "Breakage and cutting waste on masonry blockwork.",
    },
    {
        "category": "brickwork",
        "label": "Brickwork (breakage + cuts)",
        "factor": Decimal("1.05"),
        "note": "Breakage and cutting waste on facing and common brickwork.",
    },
    {
        "category": "plaster",
        "label": "Plaster / render (mixing + spillage)",
        "factor": Decimal("1.15"),
        "note": "Mixing loss and spillage on wet plaster and render.",
    },
    {
        "category": "screed",
        "label": "Floor screed (spillage)",
        "factor": Decimal("1.05"),
        "note": "Spillage and level tolerance on sand-cement screed.",
    },
    {
        "category": "timber",
        "label": "Timber / carpentry (offcuts)",
        "factor": Decimal("1.10"),
        "note": "Offcuts and defect cutting on structural and joinery timber.",
    },
    {
        "category": "insulation",
        "label": "Insulation (cuts + fitting)",
        "factor": Decimal("1.07"),
        "note": "Cutting and fitting waste on board and roll insulation.",
    },
    {
        "category": "structural steel",
        "label": "Structural steel (offcuts)",
        "factor": Decimal("1.02"),
        "note": "Small offcut allowance on fabricated structural steel.",
    },
]


async def seed_waste_factors(
    session: AsyncSession,
    *,
    tenant_id: UUID | None = None,
) -> dict[str, int]:
    """Idempotently insert the default factor library for one tenant scope.

    Skips any category already present for ``tenant_id`` (global rows use
    ``tenant_id IS NULL``), so repeated calls never duplicate a factor. Safe to
    run on every startup.

    Args:
        session: Active async SQLAlchemy session.
        tenant_id: Tenant to seed for, or ``None`` for the global library.

    Returns:
        A ``{"inserted", "skipped", "total_after"}`` count summary, where
        ``total_after`` is the number of distinct categories in scope once the
        seed has run.
    """
    from sqlalchemy import select

    from app.modules.waste_factors.models import WasteFactor
    from app.modules.waste_factors.waste_math import normalize_category

    stmt = select(WasteFactor.category)
    if tenant_id is None:
        stmt = stmt.where(WasteFactor.tenant_id.is_(None))
    else:
        stmt = stmt.where(
            (WasteFactor.tenant_id == tenant_id) | (WasteFactor.tenant_id.is_(None)),
        )
    existing_rows = (await session.execute(stmt)).scalars().all()
    existing = {normalize_category(row) for row in existing_rows}

    inserted = 0
    skipped = 0
    for row in DEFAULT_WASTE_FACTORS:
        category = str(row["category"])
        if normalize_category(category) in existing:
            skipped += 1
            continue
        note = row.get("note")
        session.add(
            WasteFactor(
                category=category,
                label=str(row["label"]),
                factor=Decimal(str(row["factor"])),
                note=str(note) if note is not None else None,
                tenant_id=tenant_id,
            ),
        )
        existing.add(normalize_category(category))
        inserted += 1

    await session.flush()
    logger.info("Waste-factor seed: inserted=%d skipped=%d", inserted, skipped)
    return {"inserted": inserted, "skipped": skipped, "total_after": len(existing)}
