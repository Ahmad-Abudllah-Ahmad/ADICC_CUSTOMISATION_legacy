# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Built-in queryable entity: ``boq_position``.

A BOQ position has no direct ``project_id`` column: it reaches a project through
its owning BOQ (``Position.boq_id -> BOQ.project_id``). So the project pin cannot
be a simple column comparison; the entity supplies a ``project_subquery`` that
returns the set of position primary keys belonging to a project (optionally
further restricted to a workspace's projects). The scoper ANDs
``Position.id IN (<subquery>)``, so a position whose BOQ left the project or
workspace is invisible.
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

ENTITY_TYPE = "boq_position"


def _position_project_subquery(
    project_id: uuid.UUID,
    restrict_project_ids: Select | None = None,
) -> Select:
    """Position ids whose BOQ belongs to ``project_id`` (and optional workspace).

    Args:
        project_id: The pinned project.
        restrict_project_ids: An optional scalar subquery of project ids the BOQ's
            project must additionally be in (the workspace narrowing).

    Returns:
        A scalar subquery of ``Position.id``.
    """
    from app.modules.boq.models import BOQ, Position

    boq_filter = BOQ.project_id == project_id
    boq_ids = select(BOQ.id).where(boq_filter)
    if restrict_project_ids is not None:
        boq_ids = boq_ids.where(BOQ.project_id.in_(restrict_project_ids))
    return select(Position.id).where(Position.boq_id.in_(boq_ids))


def build_entity() -> QueryableEntity:
    """Construct the ``boq_position`` queryable entity."""
    from app.modules.boq.models import Position

    fields = {
        "ordinal": FieldSpec(name="ordinal", column="ordinal", kind="string"),
        "description": FieldSpec(name="description", column="description", kind="string"),
        "unit": FieldSpec(name="unit", column="unit", kind="string"),
        "quantity": FieldSpec(name="quantity", column="quantity", kind="number"),
        "unit_rate": FieldSpec(name="unit_rate", column="unit_rate", kind="number"),
        "total": FieldSpec(name="total", column="total", kind="number"),
        "source": FieldSpec(
            name="source",
            column="source",
            kind="enum",
            enum_values=("manual", "cad_import", "ai_takeoff", "gaeb_import"),
        ),
        "validation_status": FieldSpec(
            name="validation_status",
            column="validation_status",
            kind="enum",
            enum_values=("pending", "passed", "warnings", "errors"),
        ),
        "reference_code": FieldSpec(name="reference_code", column="reference_code", kind="string"),
        "created_at": FieldSpec(name="created_at", column="created_at", kind="date"),
    }
    return QueryableEntity(
        entity_type=ENTITY_TYPE,
        model=Position,
        fields=fields,
        scoper=project_member_scoper,
        # No direct project FK: pin via the BOQ subquery instead.
        project_fk_column=None,
        project_subquery=_position_project_subquery,
        default_sort=("created_at", "desc"),
        default_columns=("ordinal", "description", "unit", "quantity", "unit_rate", "total"),
    )


def register() -> None:
    """Register the ``boq_position`` entity with the global registry."""
    register_queryable_entity(build_entity())
