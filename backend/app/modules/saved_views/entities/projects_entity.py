# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Built-in queryable entity: ``project``.

The project itself is project-scoped on its own primary key: the scoper pins
``Project.id == ctx.project_id``, so a saved project view resolves at most the
one project the run is pinned to (and only when the caller has access to it).
"""

from __future__ import annotations

from app.modules.saved_views.registry import (
    FieldSpec,
    QueryableEntity,
    register_queryable_entity,
)
from app.modules.saved_views.scoper import project_member_scoper

ENTITY_TYPE = "project"


def build_entity() -> QueryableEntity:
    """Construct the ``project`` queryable entity."""
    from app.modules.projects.models import Project

    fields = {
        "name": FieldSpec(name="name", column="name", kind="string"),
        "status": FieldSpec(
            name="status",
            column="status",
            kind="enum",
            enum_values=("active", "archived", "on_hold", "completed"),
        ),
        "region": FieldSpec(name="region", column="region", kind="string", groupable=False),
        "currency": FieldSpec(name="currency", column="currency", kind="string"),
        "classification_standard": FieldSpec(
            name="classification_standard",
            column="classification_standard",
            kind="string",
        ),
        "country_code": FieldSpec(name="country_code", column="country_code", kind="string"),
        "project_code": FieldSpec(name="project_code", column="project_code", kind="string"),
        "created_at": FieldSpec(name="created_at", column="created_at", kind="date"),
    }
    return QueryableEntity(
        entity_type=ENTITY_TYPE,
        model=Project,
        fields=fields,
        scoper=project_member_scoper,
        # The project's own primary key is the project pin (handled specially by
        # the scoper when model IS Project); declared for the validator.
        project_fk_column="id",
        default_sort=("created_at", "desc"),
        default_columns=("name", "status", "region", "currency", "created_at"),
    )


def register() -> None:
    """Register the ``project`` entity with the global registry."""
    register_queryable_entity(build_entity())
