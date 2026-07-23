# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Queryable entity registration for ``schedule_activity`` (T2.3).

An :class:`Activity` has no direct ``project_id``: it reaches a project through
its schedule (``Activity.schedule_id -> Schedule.project_id``). So the project
pin is a ``project_subquery`` (the same shape ``boq_position`` uses). Registering
the entity lets a saved layout's STATIC-column filter ride the audited
``saved_views`` whitelist + ``FilterSpec.bind`` security path; the dynamic
code/UDF predicates are handled separately by the schedule grouped query.

Only indexed columns are ``groupable`` (the registry enforces this), so grouping
on an unindexed static column is rejected at bind time with a whitelist error.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.modules.saved_views.registry import (
    FieldSpec,
    QueryableEntity,
    register_queryable_entity,
)
from app.modules.saved_views.scoper import project_member_scoper

if TYPE_CHECKING:
    from sqlalchemy import Select

ENTITY_TYPE = "schedule_activity"


def _activity_project_subquery(
    project_id: uuid.UUID,
    restrict_project_ids: Select | None = None,
) -> Select:
    """Activity ids whose schedule belongs to ``project_id`` (+ optional workspace)."""
    from app.modules.schedule.models import Activity, Schedule

    sched_filter = Schedule.project_id == project_id
    sched_ids = select(Schedule.id).where(sched_filter)
    if restrict_project_ids is not None:
        sched_ids = sched_ids.where(Schedule.project_id.in_(restrict_project_ids))
    return select(Activity.id).where(Activity.schedule_id.in_(sched_ids))


def build_activity_entity() -> QueryableEntity:
    """Construct the ``schedule_activity`` queryable entity.

    Built fresh (not necessarily registered) so it can be used to ``bind`` a
    layout's filter for save-time validation even before startup registration.
    """
    from app.modules.schedule.models import Activity

    fields = {
        "name": FieldSpec(name="name", column="name", kind="string"),
        "wbs_code": FieldSpec(name="wbs_code", column="wbs_code", kind="string"),
        # status is indexed -> the one groupable static column in v1.
        "status": FieldSpec(name="status", column="status", kind="string", groupable=True),
        "activity_type": FieldSpec(name="activity_type", column="activity_type", kind="string"),
        "start_date": FieldSpec(name="start_date", column="start_date", kind="string"),
        "end_date": FieldSpec(name="end_date", column="end_date", kind="string"),
        "duration_days": FieldSpec(name="duration_days", column="duration_days", kind="number"),
        "progress_pct": FieldSpec(name="progress_pct", column="progress_pct", kind="string"),
        "total_float": FieldSpec(name="total_float", column="total_float", kind="number"),
        "free_float": FieldSpec(name="free_float", column="free_float", kind="number"),
        "is_critical": FieldSpec(name="is_critical", column="is_critical", kind="bool"),
        "sort_order": FieldSpec(name="sort_order", column="sort_order", kind="number"),
        "created_at": FieldSpec(name="created_at", column="created_at", kind="date"),
    }
    return QueryableEntity(
        entity_type=ENTITY_TYPE,
        model=Activity,
        fields=fields,
        scoper=project_member_scoper,
        project_fk_column=None,
        project_subquery=_activity_project_subquery,
        default_sort=("sort_order", "asc"),
        default_columns=("wbs_code", "name", "start_date", "end_date", "duration_days", "status"),
    )


def register() -> None:
    """Register the ``schedule_activity`` entity (idempotent at the call site)."""
    register_queryable_entity(build_activity_entity())
