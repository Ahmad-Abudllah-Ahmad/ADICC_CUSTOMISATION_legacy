# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Endpoints for lossless schedule interchange (T1.1).

Mounted into the schedule module's main router, so these share the
``/api/v1/schedule`` prefix:

* ``GET  /schedules/{id}/export``        - the schedule as a neutral document;
* ``GET  /schedules/{id}/clean-preview`` - dry-run hygiene report (no mutation);
* ``POST /schedules/import``             - create a new schedule from a document.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.dependencies import CurrentUserId, RequirePermission, SessionDep
from app.modules.schedule.interchange_schemas import (
    CleanActionModel,
    ScheduleCleanPreviewResponse,
    ScheduleExportResponse,
    ScheduleImportRequest,
    ScheduleImportResponse,
)
from app.modules.schedule.interchange_service import ScheduleInterchangeService

interchange_router = APIRouter(tags=["schedule"])


def _service(session: SessionDep) -> ScheduleInterchangeService:
    return ScheduleInterchangeService(session)


@interchange_router.get(
    "/schedules/{schedule_id}/export",
    response_model=ScheduleExportResponse,
    summary="Export a schedule to the neutral interchange document",
    dependencies=[Depends(RequirePermission("schedule.read"))],
)
async def export_schedule(
    schedule_id: uuid.UUID,
    _user_id: CurrentUserId,
    session: SessionDep,
) -> ScheduleExportResponse:
    """Return the schedule, every activity and the full dependency network as a
    versioned, id-independent document that can be re-imported elsewhere."""
    document = await _service(session).export_schedule(schedule_id, _user_id)
    return ScheduleExportResponse(schedule_id=schedule_id, document=document)


@interchange_router.get(
    "/schedules/{schedule_id}/clean-preview",
    response_model=ScheduleCleanPreviewResponse,
    summary="Dry-run the normalise-on-import cleaner against a live schedule",
    dependencies=[Depends(RequirePermission("schedule.read"))],
)
async def clean_preview(
    schedule_id: uuid.UUID,
    _user_id: CurrentUserId,
    session: SessionDep,
) -> ScheduleCleanPreviewResponse:
    """Report what the cleaner would repair (dangling / self / duplicate links,
    bad relationship types, dangling or cyclic parents, out-of-range values) plus
    advisory health metrics. Read-only - it never changes the schedule."""
    result = await _service(session).clean_preview(schedule_id, _user_id)
    return ScheduleCleanPreviewResponse(
        schedule_id=schedule_id,
        actions=[CleanActionModel(code=a.code, target=a.target, detail=a.detail) for a in result.actions],
        stats=result.stats,
    )


@interchange_router.post(
    "/schedules/import",
    response_model=ScheduleImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new schedule from an interchange document",
    dependencies=[Depends(RequirePermission("schedule.create"))],
)
async def import_schedule(
    data: ScheduleImportRequest,
    _user_id: CurrentUserId,
    session: SessionDep,
) -> ScheduleImportResponse:
    """Create a fresh schedule from a document. With ``clean`` on (default) the
    document is normalised first and the applied repairs are returned; with it
    off a structurally broken document is rejected (HTTP 422)."""
    schedule, ref_map, rel_count, actions, stats = await _service(session).import_schedule(
        data.project_id,
        data.document,
        _user_id,
        clean=data.clean,
        name_override=data.name_override,
    )
    return ScheduleImportResponse(
        schedule_id=schedule.id,
        activity_count=len(ref_map),
        relationship_count=rel_count,
        clean_actions=[CleanActionModel(code=a.code, target=a.target, detail=a.detail) for a in actions],
        stats=stats,
        ref_map=ref_map,
    )
