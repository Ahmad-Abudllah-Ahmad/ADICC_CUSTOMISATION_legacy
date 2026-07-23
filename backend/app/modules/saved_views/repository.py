# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Data access for the saved-views module.

Pure CRUD on the ``SavedView`` / ``SavedViewRun`` rows ONLY. The repository never
runs a user view (that is the builder's job). Every list method is itself scoped
to an owner / project so the CRUD surface cannot leak other users' saved-view
DEFINITIONS either.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.saved_views.models import SavedView, SavedViewRun


class SavedViewRepository:
    """CRUD + scoped queries for saved-view definition rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, view_id: uuid.UUID) -> SavedView | None:
        """Single view by primary key, ``None`` if absent."""
        return await self.session.get(SavedView, view_id)

    async def list_for_owner(
        self,
        owner_id: uuid.UUID,
        *,
        entity_type: str | None = None,
        project_id: uuid.UUID | None = None,
    ) -> list[SavedView]:
        """Every view owned by ``owner_id``, optionally narrowed by entity / project."""
        stmt = select(SavedView).where(SavedView.owner_id == owner_id)
        if entity_type is not None:
            stmt = stmt.where(SavedView.entity_type == entity_type)
        if project_id is not None:
            stmt = stmt.where(SavedView.project_id == project_id)
        stmt = stmt.order_by(SavedView.is_pinned.desc(), SavedView.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_shared_in_project(
        self,
        project_id: uuid.UUID,
        *,
        entity_type: str | None = None,
    ) -> list[SavedView]:
        """Every project/workspace-shared view in ``project_id``.

        Excludes ``private`` views (those only list for their owner via
        :meth:`list_for_owner`).
        """
        stmt = select(SavedView).where(
            and_(
                SavedView.project_id == project_id,
                or_(
                    SavedView.share_scope == "project",
                    SavedView.share_scope == "workspace",
                ),
            )
        )
        if entity_type is not None:
            stmt = stmt.where(SavedView.entity_type == entity_type)
        stmt = stmt.order_by(SavedView.is_pinned.desc(), SavedView.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def create(self, view: SavedView) -> SavedView:
        """Persist a new view (caller commits)."""
        self.session.add(view)
        await self.session.flush()
        return view

    async def update_fields(self, view: SavedView, fields: dict[str, Any]) -> SavedView:
        """Apply a field dict to an existing view (caller commits)."""
        for key, value in fields.items():
            setattr(view, key, value)
        await self.session.flush()
        return view

    async def delete(self, view: SavedView) -> None:
        """Hard-delete a view (caller commits)."""
        await self.session.delete(view)
        await self.session.flush()

    async def record_run(self, run: SavedViewRun) -> SavedViewRun:
        """Append an audit row (caller commits)."""
        self.session.add(run)
        await self.session.flush()
        return run
