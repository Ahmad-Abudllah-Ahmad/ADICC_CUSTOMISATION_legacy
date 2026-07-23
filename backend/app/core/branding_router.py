# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Workspace white-label branding API (issue #272).

Branding used to live only in the browser's localStorage, so it never followed
the workspace to another browser or to an invited user's first (pre-auth) view
of the login page. These endpoints persist it once on the server:

    GET    /api/v1/branding/   - PUBLIC. The login page reads it before anyone
                                 signs in, so an invited user sees the workspace
                                 brand on the very first screen.
    PUT    /api/v1/branding/   - admin only. Set the workspace brand.
    DELETE /api/v1/branding/   - admin only. Clear it and revert to default.

Persistence is a small JSON file in the data dir (see
:mod:`app.core.app_branding`) - no database table, so this needs no migration.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.core.app_branding import (
    MAX_COMPANY_NAME,
    read_branding,
    reset_branding,
    write_branding,
)
from app.dependencies import RequireRole

router = APIRouter(tags=["branding"])


class BrandingResponse(BaseModel):
    """The workspace brand. ``mode`` is one of default / logo / text."""

    mode: str = "default"
    logo_data_url: str | None = None
    company_name: str = ""


class BrandingUpdate(BaseModel):
    """Admin payload to set the workspace brand.

    All fields optional so the client can send just what changed; the server
    sanitises and reconciles them (a logo wins; ``text`` needs a name) before
    persisting, so the stored trio is always consistent.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    mode: str | None = None
    logo_data_url: str | None = None
    company_name: str | None = Field(default=None, max_length=MAX_COMPANY_NAME)


@router.get("/branding/", response_model=BrandingResponse)
@router.get("/branding", response_model=BrandingResponse, include_in_schema=False)
async def get_branding() -> BrandingResponse:
    """Public: the workspace brand for the login page and the app shell."""
    return BrandingResponse(**read_branding())


@router.put(
    "/branding/",
    response_model=BrandingResponse,
    dependencies=[Depends(RequireRole("admin"))],
)
@router.put(
    "/branding",
    response_model=BrandingResponse,
    include_in_schema=False,
    dependencies=[Depends(RequireRole("admin"))],
)
async def put_branding(body: BrandingUpdate) -> BrandingResponse:
    """Admin: set the workspace brand so it persists for every browser and user."""
    return BrandingResponse(**write_branding(body.model_dump()))


@router.delete(
    "/branding/",
    response_model=BrandingResponse,
    dependencies=[Depends(RequireRole("admin"))],
)
@router.delete(
    "/branding",
    response_model=BrandingResponse,
    include_in_schema=False,
    dependencies=[Depends(RequireRole("admin"))],
)
async def delete_branding() -> BrandingResponse:
    """Admin: clear the custom brand and revert to the default."""
    return BrandingResponse(**reset_branding())
