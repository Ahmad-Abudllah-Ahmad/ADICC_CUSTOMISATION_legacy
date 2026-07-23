"""‌⁠‍{{display_name}} API routes.

Mounted automatically by the module loader at
``/api/v1/{{module_name}}/``. Add new endpoints below.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUserId, SessionDep
from app.modules.{{module_short}} import service
from app.modules.{{module_short}}.repository import ItemRepository
from app.modules.{{module_short}}.schemas import ItemCreate, ItemRead, ItemUpdate

router = APIRouter()


@router.get("/", tags=["{{module_name}}"])
async def module_info() -> dict[str, str]:
    """‌⁠‍Health-style ping so operators can confirm the module mounted."""
    return {"module": "{{module_name}}", "status": "active"}


@router.post(
    "/items",
    response_model=ItemRead,
    status_code=status.HTTP_201_CREATED,
    tags=["{{module_name}}"],
)
async def create_item(
    payload: ItemCreate,
    session: SessionDep,
    _user_id: CurrentUserId,
) -> ItemRead:
    item = await service.create_item(session, payload)
    await session.commit()
    return ItemRead.model_validate(item)


@router.get("/items", response_model=list[ItemRead], tags=["{{module_name}}"])
async def list_items(
    project_id: uuid.UUID,
    session: SessionDep,
    _user_id: CurrentUserId,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> list[ItemRead]:
    repo = ItemRepository(session)
    rows = await repo.list_for_project(project_id, offset=offset, limit=limit)
    return [ItemRead.model_validate(r) for r in rows]


@router.get("/items/{item_id}", response_model=ItemRead, tags=["{{module_name}}"])
async def get_item(
    item_id: uuid.UUID,
    session: SessionDep,
    _user_id: CurrentUserId,
) -> ItemRead:
    repo = ItemRepository(session)
    item = await repo.get_by_id(item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    return ItemRead.model_validate(item)


@router.patch("/items/{item_id}", response_model=ItemRead, tags=["{{module_name}}"])
async def update_item(
    item_id: uuid.UUID,
    payload: ItemUpdate,
    session: SessionDep,
    _user_id: CurrentUserId,
) -> ItemRead:
    item = await service.update_item(session, item_id, payload)
    await session.commit()
    return ItemRead.model_validate(item)


@router.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["{{module_name}}"],
)
async def delete_item(
    item_id: uuid.UUID,
    session: SessionDep,
    _user_id: CurrentUserId,
) -> None:
    await service.delete_item(session, item_id)
    await session.commit()
