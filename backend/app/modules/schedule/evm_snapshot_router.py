# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""EVM-snapshot API.

A read endpoint that lists a schedule's persisted EVM snapshots ordered by data
date, for charting the cost / schedule performance trend. Mounted under the same
``/api/v1/schedule`` prefix as the core schedule router.

Snapshots are produced automatically as the schedule's data date advances (see
:mod:`evm_snapshot_service`), so there is no create endpoint here. Access is gated
exactly like the sibling progress endpoints: the owning project is resolved from
the schedule and ``verify_project_access`` runs (404 on cross-tenant access,
existence-oracle safe) before any work, reusing the existing ``schedule.read``
grant - no new permission key.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.dependencies import CurrentUserId, RequirePermission, SessionDep, verify_project_access
from app.modules.schedule.evm_snapshot_schemas import EvmSnapshotListResponse, EvmSnapshotResponse
from app.modules.schedule.evm_snapshot_service import ScheduleEvmSnapshotService

evm_snapshot_router = APIRouter(tags=["schedule"])


def _get_service(session: SessionDep) -> ScheduleEvmSnapshotService:
    return ScheduleEvmSnapshotService(session)


@evm_snapshot_router.get(
    "/schedules/{schedule_id}/evm-snapshots/",
    response_model=EvmSnapshotListResponse,
    summary="List a schedule's EVM snapshots over time (trend)",
    dependencies=[Depends(RequirePermission("schedule.read"))],
)
async def list_evm_snapshots(
    schedule_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ScheduleEvmSnapshotService = Depends(_get_service),
) -> EvmSnapshotListResponse:
    schedule = await service.progress.get_schedule(schedule_id)
    await verify_project_access(schedule.project_id, user_id, session)
    snapshots = await service.list_snapshots(schedule_id)
    return EvmSnapshotListResponse(
        schedule_id=schedule_id,
        snapshots=[EvmSnapshotResponse.model_validate(s) for s in snapshots],
        count=len(snapshots),
    )
