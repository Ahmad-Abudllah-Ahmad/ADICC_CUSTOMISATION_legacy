# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""SAFETY PRIMITIVE 1 - the mandatory scoper.

Every executed query has scope predicates ANDed in server-side, derived from the
request context, before any user filter is applied. There is no code path that
runs a saved view without the scoper: the service builds the scoped base
statement here and the query builder requires that statement as an argument, so
"compile a filter" and "apply the scope" are the same call graph.

The scope values come from :class:`ScopeContext`, which is assembled from the
DB-rehydrated JWT payload (never from the saved-view row or the request body), so
a user editing the stored spec JSON cannot move themselves into another project
or workspace.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.partner_pack.scope import (
    PACK_TAG_KEY,
    active_pack_slug,
    scope_project_query,
)
from app.modules.saved_views.errors import ScopeDenied

if TYPE_CHECKING:
    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.database import Base
    from app.modules.saved_views.registry import QueryableEntity


@dataclass(frozen=True)
class ScopeContext:
    """The per-request scope anchor.

    Built once per request inside the service from ``CurrentUserId`` /
    ``CurrentUserPayload``, never from the saved-view body.

    Attributes:
        user_id: From the JWT subject, DB-rehydrated.
        role: From the DB-rehydrated payload, not the raw JWT claim.
        project_id: The project the run is pinned to (from URL / query).
        workspace_slug: The active partner-pack slug captured at request time.
        is_admin: True when ``role == "admin"``.
    """

    user_id: uuid.UUID
    role: str
    project_id: uuid.UUID | None
    workspace_slug: str | None
    is_admin: bool

    @classmethod
    def from_payload(
        cls,
        *,
        user_id: str | uuid.UUID,
        payload: dict | None,
        project_id: uuid.UUID | None,
    ) -> ScopeContext:
        """Assemble a context from a DB-rehydrated payload and a path project_id.

        ``active_pack_slug()`` is captured here, at request time, so a later pack
        change cannot retroactively widen a scope already in flight.
        """
        role = ""
        if payload is not None:
            role = str(payload.get("role", "") or "")
        return cls(
            user_id=uuid.UUID(str(user_id)),
            role=role,
            project_id=project_id,
            workspace_slug=active_pack_slug(),
            is_admin=role == "admin",
        )


class ProjectMemberScoper:
    """The default scoper for every Phase 1 entity.

    Enforces three independent narrowings, all ANDed:

        1. PROJECT pin - constrains rows to ``ctx.project_id``.
        2. ACCESS check - ``verify_project_access`` (404 on non-membership), so a
           user cannot even name a project they cannot see. Admin bypasses this
           check but NOT the pins below.
        3. WORKSPACE pin - when a partner pack is active, constrains the row's
           project to that pack, so a child row whose project left the workspace
           is invisible too.
    """

    async def scope(
        self,
        stmt: Select,
        model: type[Base],
        ctx: ScopeContext,
        session: AsyncSession,
    ) -> Select:
        """Return ``stmt`` narrowed by the project pin, access check, and workspace pin."""
        from app.dependencies import verify_project_access
        from app.modules.projects.models import Project

        if ctx.project_id is None:
            # A saved view always runs inside a project. No project means no
            # base statement - refuse rather than build an unscoped query.
            raise ScopeDenied("A saved view must run inside a project")

        entity = _entity_for_model(model)

        # 1. PROJECT pin.
        if entity is not None and entity.project_subquery is not None:
            subq = entity.project_subquery(ctx.project_id)
            stmt = stmt.where(model.id.in_(subq))
        elif model is Project:
            stmt = stmt.where(Project.id == ctx.project_id)
        else:
            project_fk = _project_fk_attr(model, entity)
            stmt = stmt.where(project_fk == ctx.project_id)

        # 2. ACCESS check. Raises 404 (HTTPException) when the user is not
        # owner/admin/team-member. Admin is allowed through by the helper, which
        # is exactly the documented behaviour - admin still keeps the pins.
        try:
            await verify_project_access(ctx.project_id, str(ctx.user_id), session)
        except Exception as exc:  # noqa: BLE001 - normalise to a scope refusal
            from fastapi import HTTPException

            if isinstance(exc, HTTPException) and exc.status_code == 404:
                raise ScopeDenied("Project not found or access denied") from exc
            raise

        # 3. WORKSPACE pin.
        if ctx.workspace_slug:
            if model is Project:
                stmt = scope_project_query(stmt, Project)
            else:
                pack_project_ids = select(Project.id).where(
                    Project.metadata_[PACK_TAG_KEY].as_string() == ctx.workspace_slug
                )
                if entity is not None and entity.project_subquery is not None:
                    # Child reached via subquery: pin the row's primary key to a
                    # project that is still inside the workspace.
                    workspace_subq = entity.project_subquery(ctx.project_id, pack_project_ids)
                    stmt = stmt.where(model.id.in_(workspace_subq))
                else:
                    project_fk = _project_fk_attr(model, entity)
                    stmt = stmt.where(project_fk.in_(pack_project_ids))

        return stmt


def _entity_for_model(model: type[Base]) -> QueryableEntity | None:
    """Look up the registered entity whose model is ``model`` (first match)."""
    from app.modules.saved_views.registry import entity_registry

    for entity in entity_registry.all().values():
        if entity.model is model:
            return entity
    return None


def _project_fk_attr(model: type[Base], entity: QueryableEntity | None):  # noqa: ANN202
    """Resolve the project-FK ORM attribute the scoper pins on."""
    column_name = "project_id"
    if entity is not None and entity.project_fk_column:
        column_name = entity.project_fk_column
    return getattr(model, column_name)


# A single shared instance is enough; the scoper is stateless.
project_member_scoper = ProjectMemberScoper()
