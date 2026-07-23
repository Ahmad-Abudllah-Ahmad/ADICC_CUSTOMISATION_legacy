# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Module management API - list, enable, disable modules at runtime.

Provides RESTful endpoints for the frontend Modules page to interact
with the :class:`~app.core.module_loader.ModuleLoader`.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.module_loader import module_loader
from app.dependencies import RequirePermission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/modules", tags=["Module Management"])


@router.get("/")
async def list_all_modules() -> list[dict[str, Any]]:
    """List all discovered modules with enabled/disabled status."""
    return module_loader.list_modules()


@router.get("/{module_name}")
async def get_module_detail(module_name: str) -> dict[str, Any]:
    """Get detailed info about a module."""
    try:
        return module_loader.get_module_info(module_name)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module '{module_name}' not found.",
        )


@router.post(
    "/{module_name}/enable",
    dependencies=[Depends(RequirePermission("admin"))],
)
async def enable_module(module_name: str, request: Request) -> dict[str, Any]:
    """Enable a module (admin only)."""
    if module_name not in module_loader._manifests:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module '{module_name}' not found.",
        )

    try:
        result = await module_loader.enable_module(module_name, request.app)
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/{module_name}/disable",
    dependencies=[Depends(RequirePermission("admin"))],
)
async def disable_module(module_name: str, request: Request) -> dict[str, Any]:
    """Disable a module (admin only). Fails if other enabled modules depend on it."""
    if module_name not in module_loader._manifests:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module '{module_name}' not found.",
        )

    try:
        result = await module_loader.disable_module(module_name, request.app)
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get("/dependency-tree/{module_name}")
async def get_dependency_tree(module_name: str) -> dict[str, Any]:
    """Show which modules depend on this module."""
    try:
        return module_loader.get_dependency_tree(module_name)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module '{module_name}' not found.",
        )
