# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo seed data for the production-norm expansion module.

Loaded on demand (and best-effort on module startup) via
``await seed_norm_expansion(session)``. It inserts a handful of illustrative
norms - internal plastering per m2, wall formwork per m2 and structural
concrete per m3 - so the norm library and the expand panel are never empty on a
fresh install.

The coefficients are deliberately round placeholders: they show the shape of a
production norm (labour-hours, machine-hours and material quantities per unit)
without claiming to be a calibrated regional standard. Every value is stored as
``Decimal``.

The seed is idempotent: it returns an empty dict immediately when any norm
already exists.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.norm_expansion.models import NormMaterial, ProductionNorm

logger = logging.getLogger(__name__)

# Each entry: work_key, name, unit, category, labor h/unit, machine h/unit,
# and its materials as (name, unit, qty_per_unit).
_DEMO_NORMS: list[dict[str, object]] = [
    {
        "work_key": "plastering_internal",
        "name": "Internal plastering, gypsum, 15 mm",
        "unit": "m2",
        "category": "finishing",
        "labor_hours_per_unit": Decimal("0.45"),
        "machine_hours_per_unit": Decimal("0.02"),
        "materials": [
            ("Gypsum plaster", "kg", Decimal("12.0")),
            ("Water", "l", Decimal("6.0")),
        ],
    },
    {
        "work_key": "formwork_wall",
        "name": "Wall formwork, plywood, per contact area",
        "unit": "m2",
        "category": "concrete",
        "labor_hours_per_unit": Decimal("0.70"),
        "machine_hours_per_unit": Decimal("0.05"),
        "materials": [
            ("Plywood sheathing", "m2", Decimal("1.05")),
            ("Timber studs", "m", Decimal("3.5")),
            ("Form-release oil", "l", Decimal("0.2")),
            ("Nails", "kg", Decimal("0.15")),
        ],
    },
    {
        "work_key": "concrete_c30_37",
        "name": "Structural concrete C30/37, placed",
        "unit": "m3",
        "category": "concrete",
        "labor_hours_per_unit": Decimal("1.20"),
        "machine_hours_per_unit": Decimal("0.35"),
        "materials": [
            ("Ready-mix concrete C30/37", "m3", Decimal("1.02")),
            ("Curing compound", "l", Decimal("0.25")),
        ],
    },
]


async def seed_norm_expansion(session: AsyncSession) -> dict[str, int]:
    """Insert the demo production norms if the library is empty.

    Args:
        session: Active async SQLAlchemy session.

    Returns:
        A dict with the number of norms and materials inserted (both zero when
        the seed short-circuits because norms already exist).
    """
    existing = await session.execute(select(ProductionNorm.id).limit(1))
    if existing.scalar_one_or_none() is not None:
        return {"norms": 0, "materials": 0}

    norms_added = 0
    materials_added = 0
    for spec in _DEMO_NORMS:
        materials = spec["materials"]  # type: ignore[assignment]
        norm = ProductionNorm(
            work_key=spec["work_key"],
            name=spec["name"],
            unit=spec["unit"],
            category=spec["category"],
            labor_hours_per_unit=spec["labor_hours_per_unit"],
            machine_hours_per_unit=spec["machine_hours_per_unit"],
            notes="Demo placeholder coefficients.",
            is_active=True,
        )
        for order, (mat_name, mat_unit, qty) in enumerate(materials):  # type: ignore[arg-type]
            norm.materials.append(
                NormMaterial(
                    name=mat_name,
                    unit=mat_unit,
                    qty_per_unit=qty,
                    sort_order=order,
                )
            )
            materials_added += 1
        session.add(norm)
        norms_added += 1

    await session.flush()
    logger.info("Norm-expansion seed inserted: norms=%d materials=%d", norms_added, materials_added)
    return {"norms": norms_added, "materials": materials_added}
