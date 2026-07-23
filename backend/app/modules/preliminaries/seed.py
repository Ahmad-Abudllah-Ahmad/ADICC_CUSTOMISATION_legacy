# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Starter checklist of common preliminaries items.

The estimator does not ship priced preliminaries - rates and durations are always
project specific, so amounts are entered by the user. What it ships is a starter
*checklist*: the common general-conditions items an estimator would otherwise
retype on every job (site office, supervision, temporary power, scaffolding,
final clean and so on), each tagged with a sensible category and whether it is
normally time-related or a fixed one-off.

Two entry points:

* :func:`starter_checklist` returns the suggestions as plain dicts (no amounts) -
  the router serves these so the UI can offer one-click "add this item" chips.
* :func:`seed_preliminaries` materialises the checklist as zero-amount rows for a
  demo project so a fresh project opens with the list ready to fill in. It is
  idempotent: it skips any project that already has preliminaries items.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.preliminaries.models import ITEM_TYPE_FIXED, ITEM_TYPE_TIME_RELATED, PrelimItem

logger = logging.getLogger(__name__)

# (label, category, item_type). Categories match the model docstring buckets:
# site_establishment, site_staff, temporary_works, standing_plant, welfare, general.
_STARTER_CHECKLIST: list[tuple[str, str, str]] = [
    ("Site office and cabins", "site_establishment", ITEM_TYPE_TIME_RELATED),
    ("Site set-up and mobilisation", "site_establishment", ITEM_TYPE_FIXED),
    ("Hoarding, fencing and gates", "site_establishment", ITEM_TYPE_FIXED),
    ("Project management and supervision", "site_staff", ITEM_TYPE_TIME_RELATED),
    ("Site engineer", "site_staff", ITEM_TYPE_TIME_RELATED),
    ("Health and safety provision", "site_staff", ITEM_TYPE_TIME_RELATED),
    ("Temporary power", "temporary_works", ITEM_TYPE_TIME_RELATED),
    ("Temporary water and drainage", "temporary_works", ITEM_TYPE_TIME_RELATED),
    ("Scaffolding and access", "temporary_works", ITEM_TYPE_TIME_RELATED),
    ("Standing crane and hoist", "standing_plant", ITEM_TYPE_TIME_RELATED),
    ("Small plant and tools", "standing_plant", ITEM_TYPE_TIME_RELATED),
    ("Welfare facilities", "welfare", ITEM_TYPE_TIME_RELATED),
    ("Site cleaning", "welfare", ITEM_TYPE_TIME_RELATED),
    ("Final clean on completion", "general", ITEM_TYPE_FIXED),
    ("Insurances and bonds", "general", ITEM_TYPE_FIXED),
]


def starter_checklist() -> list[dict[str, str]]:
    """Return the starter checklist as ``[{label, category, item_type}]`` dicts.

    Pure and database-free (used by the router to offer suggestions). Amounts are
    deliberately absent - the user enters the rate, periods or fixed amount.
    """
    return [
        {"label": label, "category": category, "item_type": item_type}
        for label, category, item_type in _STARTER_CHECKLIST
    ]


async def seed_preliminaries(
    session: AsyncSession,
    project_ids: list[uuid.UUID],
) -> dict[str, int]:
    """Materialise the starter checklist as zero-amount rows for demo projects.

    Seeds at most the first three project ids. Idempotent: a project that already
    has any preliminaries item is skipped, so re-running never duplicates the
    checklist. Amounts are left at zero for the user to fill in.

    Args:
        session: Active async SQLAlchemy session.
        project_ids: Project ids to seed (first three are covered).

    Returns:
        ``{"items": <rows inserted>}``.
    """
    if not project_ids:
        return {"items": 0}

    inserted = 0
    for project_id in project_ids[:3]:
        existing = await session.execute(
            select(PrelimItem.id).where(PrelimItem.project_id == project_id).limit(1),
        )
        if existing.scalar_one_or_none() is not None:
            continue
        for sort_order, (label, category, item_type) in enumerate(_STARTER_CHECKLIST):
            item: dict[str, Any] = {
                "project_id": project_id,
                "label": label,
                "category": category,
                "item_type": item_type,
                "sort_order": sort_order,
            }
            session.add(PrelimItem(**item))
            inserted += 1

    await session.flush()
    logger.info("Preliminaries seed inserted %d starter item(s)", inserted)
    return {"items": inserted}
