# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Timeline service - read queries over the existing activity-log store.

The timeline is a cross-module rollup view. A row belongs to a project's
timeline when either:

* it was logged with ``parent_entity_id`` == the project id (the normal case
  for module events that carry their umbrella project - RFIs, NCRs, change
  orders, ...), or
* it was logged directly against the project itself
  (``entity_id`` == the project id), e.g. a ``project.status_changed`` row.

No new table and no migration: this reads :class:`app.core.audit_log.ActivityLog`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import ActivityLog


def _project_scope(project_id: str | uuid.UUID):
    """SQLAlchemy predicate selecting rows that belong to a project's timeline.

    A row is in scope when its ``parent_entity_id`` is the project (module
    events rolled up to their umbrella project) OR its ``entity_id`` is the
    project (events logged directly against the project row).
    """
    pid = str(project_id)
    return or_(
        ActivityLog.parent_entity_id == pid,
        ActivityLog.entity_id == pid,
    )


def _apply_filters(
    stmt,
    *,
    modules: list[str] | None,
    actions: list[str] | None,
    entity_type: str | None,
    since: datetime | None,
    until: datetime | None,
):
    """Apply the optional timeline filters to a select statement."""
    if modules:
        stmt = stmt.where(ActivityLog.module.in_(list(modules)))
    if actions:
        stmt = stmt.where(ActivityLog.action.in_(list(actions)))
    if entity_type is not None:
        stmt = stmt.where(ActivityLog.entity_type == entity_type)
    if since is not None:
        stmt = stmt.where(ActivityLog.created_at >= since)
    if until is not None:
        stmt = stmt.where(ActivityLog.created_at <= until)
    return stmt


async def get_project_timeline(
    session: AsyncSession,
    *,
    project_id: str | uuid.UUID,
    modules: list[str] | None = None,
    actions: list[str] | None = None,
    entity_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[ActivityLog]:
    """Newest-first slice of a project's cross-module activity timeline.

    Args:
        session: Active async session.
        project_id: The umbrella project to roll activity up to.
        modules: Optional ``module`` allowlist (e.g. ``["rfi", "ncr"]``).
        actions: Optional ``action`` allowlist (full event names).
        entity_type: Optional exact ``entity_type`` filter.
        since / until: Optional inclusive ``created_at`` bounds (UTC).
        limit: Max rows to return (clamped to a sane window by the caller).
        offset: Pagination offset.

    Returns:
        A list of :class:`ActivityLog` rows ordered by ``created_at`` DESC.
    """
    stmt = select(ActivityLog).where(_project_scope(project_id))
    stmt = _apply_filters(
        stmt,
        modules=modules,
        actions=actions,
        entity_type=entity_type,
        since=since,
        until=until,
    )
    stmt = stmt.order_by(ActivityLog.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_project_timeline(
    session: AsyncSession,
    *,
    project_id: str | uuid.UUID,
    modules: list[str] | None = None,
    actions: list[str] | None = None,
    entity_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> int:
    """Total number of timeline rows for a project under the same filters.

    Mirrors :func:`get_project_timeline` so the API can return an accurate
    ``total`` for pagination without re-fetching every row.
    """
    stmt = select(func.count()).select_from(ActivityLog).where(_project_scope(project_id))
    stmt = _apply_filters(
        stmt,
        modules=modules,
        actions=actions,
        entity_type=entity_type,
        since=since,
        until=until,
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)
