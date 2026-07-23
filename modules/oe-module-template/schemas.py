"""‌⁠‍{{display_name}} Pydantic schemas — request / response shapes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ItemCreate(BaseModel):
    """‌⁠‍Payload accepted by ``POST /v1/{{module_name}}/items``."""

    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=5000)
    project_id: UUID


class ItemUpdate(BaseModel):
    """‌⁠‍Partial-update payload — every field is optional."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)


class ItemRead(BaseModel):
    """‌⁠‍Response shape returned by the router."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    project_id: UUID
    created_at: datetime
    updated_at: datetime
