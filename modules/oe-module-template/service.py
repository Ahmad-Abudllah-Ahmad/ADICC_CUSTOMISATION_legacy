"""‌⁠‍{{display_name}} service — thin business-logic layer.

Service functions are stateless, accept an ``AsyncSession`` plus
domain primitives, and raise :class:`fastapi.HTTPException` for
caller-visible failures. They orchestrate :mod:`repository` calls
and (optionally) publish events on the global event bus.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import event_bus
from app.modules.{{module_short}}.models import Item
from app.modules.{{module_short}}.repository import ItemRepository
from app.modules.{{module_short}}.schemas import ItemCreate, ItemUpdate


async def create_item(session: AsyncSession, payload: ItemCreate) -> Item:
    """‌⁠‍Insert a new item, publish ``{{module_name}}.item.created``."""
    repo = ItemRepository(session)
    item = Item(
        name=payload.name.strip(),
        description=payload.description.strip(),
        project_id=payload.project_id,
    )
    item = await repo.create(item)
    try:
        event_bus.publish_detached(
            "{{module_name}}.item.created",
            {"id": str(item.id), "project_id": str(item.project_id)},
            source_module="{{module_name}}",
        )
    except Exception:  # noqa: BLE001 — event bus is best-effort
        pass
    return item


async def update_item(
    session: AsyncSession,
    item_id: uuid.UUID,
    payload: ItemUpdate,
) -> Item:
    """‌⁠‍Patch an item in place. 404 if missing."""
    repo = ItemRepository(session)
    item = await repo.get_by_id(item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    if payload.name is not None:
        item.name = payload.name.strip()
    if payload.description is not None:
        item.description = payload.description.strip()
    await session.flush()
    return item


async def delete_item(session: AsyncSession, item_id: uuid.UUID) -> None:
    """‌⁠‍Hard-delete an item. 404 if missing."""
    repo = ItemRepository(session)
    if not await repo.delete(item_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
