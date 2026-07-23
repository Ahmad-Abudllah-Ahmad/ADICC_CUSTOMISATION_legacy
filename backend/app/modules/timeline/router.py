# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Timeline API routes (auto-mounted at /api/v1/timeline).

A unified, cross-module project timeline read over the existing activity-log
store. The only endpoint returns a paginated, newest-first feed for one
project, with optional module / action / entity-type / date-range filters.

Access control mirrors every other project-scoped router: the caller must be
authenticated (``CurrentUserId``) and pass :func:`verify_project_access` for
the requested project (owner / team-member / admin), which 404s on both
"missing" and "denied" to avoid leaking project existence.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Query

from app.dependencies import CurrentUserId, SessionDep, verify_project_access
from app.modules.timeline.schemas import TimelineEntry, TimelineResponse
from app.modules.timeline.service import count_project_timeline, get_project_timeline

router = APIRouter(tags=["Timeline"])
logger = logging.getLogger(__name__)


def _to_entry(row) -> TimelineEntry:
    """Map one ActivityLog ORM row onto a TimelineEntry.

    Done explicitly (not ``from_attributes``) because the ORM stores the JSON
    payload on ``metadata_`` while the schema field is ``metadata``.
    """
    return TimelineEntry(
        id=row.id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        action=row.action,
        module=row.module,
        from_status=row.from_status,
        to_status=row.to_status,
        parent_entity_type=row.parent_entity_type,
        parent_entity_id=row.parent_entity_id,
        actor_id=row.actor_id,
        reason=row.reason,
        metadata=row.metadata_ or {},
        created_at=row.created_at,
    )


@router.get("/projects/{project_id}", response_model=TimelineResponse)
async def get_project_timeline_endpoint(
    project_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    module: list[str] | None = Query(
        default=None,
        description="Filter to one or more logical modules (e.g. rfi, ncr).",
    ),
    action: list[str] | None = Query(
        default=None,
        description="Filter to one or more full event-name actions.",
    ),
    entity_type: str | None = Query(
        default=None,
        description="Filter to an exact entity_type.",
    ),
    since: datetime | None = Query(
        default=None,
        description="Inclusive lower bound on created_at (UTC).",
    ),
    until: datetime | None = Query(
        default=None,
        description="Inclusive upper bound on created_at (UTC).",
    ),
    limit: int = Query(default=100, ge=1, le=500, description="Max entries to return."),
    offset: int = Query(default=0, ge=0, description="Pagination offset."),
) -> TimelineResponse:
    """Unified, newest-first activity timeline for a single project."""
    await verify_project_access(project_id, user_id or "", session)

    rows = await get_project_timeline(
        session,
        project_id=project_id,
        modules=module,
        actions=action,
        entity_type=entity_type,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    total = await count_project_timeline(
        session,
        project_id=project_id,
        modules=module,
        actions=action,
        entity_type=entity_type,
        since=since,
        until=until,
    )
    return TimelineResponse(
        entries=[_to_entry(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
