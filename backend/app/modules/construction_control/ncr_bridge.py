# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Shared NCR-raise bridge for the construction-control module.

The failed-inspection -> NCR bridge first shipped on ``ConstructionControlService``
(Pillar 1). As later pillars (as-built records, gates) also need to raise a
non-conformance without instantiating the inspection service, the low-level call into
the NCR module is extracted here as one reusable coroutine.

It is intentionally tiny: callers assemble the human description and the metadata, this
helper performs the lazy import and the create. The lazy import keeps construction-control
degrading gracefully if the NCR module is ever disabled.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


async def raise_ncr(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    title: str,
    description: str,
    ncr_type: str,
    severity: str,
    user_id: str | None,
    linked_inspection_id: str | None = None,
    location_description: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Create an NCR through the NCR module and return its id as a string.

    Lazy-imported so the construction-control module records the failure without an NCR
    if the NCR module is disabled.
    """
    from app.modules.ncr.schemas import NCRCreate
    from app.modules.ncr.service import NCRService

    data = NCRCreate(
        project_id=project_id,
        title=title[:500],
        description=description[:10000],
        ncr_type=ncr_type,
        severity=severity,
        status="identified",
        location_description=location_description,
        linked_inspection_id=linked_inspection_id,
        metadata=metadata or {},
    )
    ncr = await NCRService(session).create_ncr(data, user_id=user_id)
    return str(ncr.id)
