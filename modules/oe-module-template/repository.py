"""‌⁠‍{{display_name}} data access layer.

Pure queries — no HTTP, no business logic. Each method takes an
``AsyncSession`` and returns model instances or primitives. The
``service`` layer composes these calls into a workflow.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.{{module_short}}.models import Item


class ItemRepository:
    """‌⁠‍CRUD for :class:`Item`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, item_id: uuid.UUID) -> Item | None:
        return await self.session.get(Item, item_id)

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Item]:
        stmt = (
            select(Item)
            .where(Item.project_id == project_id)
            .order_by(Item.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, item: Item) -> Item:
        self.session.add(item)
        await self.session.flush()
        return item

    async def delete(self, item_id: uuid.UUID) -> bool:
        item = await self.get_by_id(item_id)
        if item is None:
            return False
        await self.session.delete(item)
        await self.session.flush()
        return True
