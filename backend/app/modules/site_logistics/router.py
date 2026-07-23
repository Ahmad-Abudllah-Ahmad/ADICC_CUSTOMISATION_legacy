# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site Logistics & Delivery API routes.

Route prefix: /api/v1/site-logistics

    GET    /gates/                         - list gates
    POST   /gates/                         - create gate
    GET    /gates/{gate_id}                - get gate
    PATCH  /gates/{gate_id}                - update gate
    DELETE /gates/{gate_id}                - delete gate

    GET    /laydown-zones/                 - list laydown zones
    POST   /laydown-zones/                 - create laydown zone
    GET    /laydown-zones/{zone_id}        - get laydown zone
    PATCH  /laydown-zones/{zone_id}        - update laydown zone
    DELETE /laydown-zones/{zone_id}        - delete laydown zone

    GET    /deliveries/                    - list deliveries (filter by day/gate/status)
    POST   /deliveries/                    - book delivery
    GET    /deliveries/{delivery_id}       - get delivery
    PATCH  /deliveries/{delivery_id}       - update delivery
    DELETE /deliveries/{delivery_id}       - delete delivery
    POST   /deliveries/{delivery_id}/approve/ - approve delivery
    POST   /deliveries/{delivery_id}/reject/  - reject delivery

    GET    /stats/                         - aggregate delivery stats
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.dependencies import (
    CurrentUserId,
    RequirePermission,
    SessionDep,
    verify_project_access,
)
from app.modules.site_logistics.schemas import (
    DeliveryCreate,
    DeliveryDecisionRequest,
    DeliveryResponse,
    DeliveryUpdate,
    GateCreate,
    GateResponse,
    GateUpdate,
    LaydownZoneCreate,
    LaydownZoneResponse,
    LaydownZoneUpdate,
    SiteLogisticsStatsResponse,
)
from app.modules.site_logistics.service import SiteLogisticsService

router = APIRouter(tags=["site-logistics"])
logger = logging.getLogger(__name__)


def _get_service(session: SessionDep) -> SiteLogisticsService:
    return SiteLogisticsService(session)


# ── Response builders (hand-built to read the JSON ``metadata_`` column, never
# SQLAlchemy's class-level ``metadata`` registry) ─────────────────────────────


def _gate_to_response(gate: object) -> GateResponse:
    return GateResponse(
        id=gate.id,  # type: ignore[attr-defined]
        project_id=gate.project_id,  # type: ignore[attr-defined]
        name=gate.name,  # type: ignore[attr-defined]
        open_time=gate.open_time,  # type: ignore[attr-defined]
        close_time=gate.close_time,  # type: ignore[attr-defined]
        capacity_per_slot=gate.capacity_per_slot,  # type: ignore[attr-defined]
        notes=gate.notes,  # type: ignore[attr-defined]
        created_by=gate.created_by,  # type: ignore[attr-defined]
        metadata=getattr(gate, "metadata_", {}),
        created_at=gate.created_at,  # type: ignore[attr-defined]
        updated_at=gate.updated_at,  # type: ignore[attr-defined]
    )


def _zone_to_response(zone: object) -> LaydownZoneResponse:
    return LaydownZoneResponse(
        id=zone.id,  # type: ignore[attr-defined]
        project_id=zone.project_id,  # type: ignore[attr-defined]
        name=zone.name,  # type: ignore[attr-defined]
        capacity_desc=zone.capacity_desc,  # type: ignore[attr-defined]
        usage_note=zone.usage_note,  # type: ignore[attr-defined]
        created_by=zone.created_by,  # type: ignore[attr-defined]
        metadata=getattr(zone, "metadata_", {}),
        created_at=zone.created_at,  # type: ignore[attr-defined]
        updated_at=zone.updated_at,  # type: ignore[attr-defined]
    )


def _delivery_to_response(delivery: object) -> DeliveryResponse:
    return DeliveryResponse(
        id=delivery.id,  # type: ignore[attr-defined]
        project_id=delivery.project_id,  # type: ignore[attr-defined]
        gate_id=delivery.gate_id,  # type: ignore[attr-defined]
        supplier_name=delivery.supplier_name,  # type: ignore[attr-defined]
        contact_name=delivery.contact_name,  # type: ignore[attr-defined]
        contact_phone=delivery.contact_phone,  # type: ignore[attr-defined]
        vehicle_type=delivery.vehicle_type,  # type: ignore[attr-defined]
        materials_desc=delivery.materials_desc,  # type: ignore[attr-defined]
        window_start=delivery.window_start,  # type: ignore[attr-defined]
        window_end=delivery.window_end,  # type: ignore[attr-defined]
        status=delivery.status,  # type: ignore[attr-defined]
        po_ref=delivery.po_ref,  # type: ignore[attr-defined]
        notes=delivery.notes,  # type: ignore[attr-defined]
        created_by=delivery.created_by,  # type: ignore[attr-defined]
        metadata=getattr(delivery, "metadata_", {}),
        created_at=delivery.created_at,  # type: ignore[attr-defined]
        updated_at=delivery.updated_at,  # type: ignore[attr-defined]
    )


# ── Gates ─────────────────────────────────────────────────────────────────────


@router.get(
    "/gates",
    response_model=list[GateResponse],
    dependencies=[Depends(RequirePermission("site_logistics.read"))],
    include_in_schema=False,
)
@router.get(
    "/gates/",
    response_model=list[GateResponse],
    dependencies=[Depends(RequirePermission("site_logistics.read"))],
)
async def list_gates(
    user_id: CurrentUserId,
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    service: SiteLogisticsService = Depends(_get_service),
) -> list[GateResponse]:
    """List site access gates for a project."""
    await verify_project_access(project_id, user_id, session)
    gates = await service.list_gates(project_id)
    return [_gate_to_response(g) for g in gates]


@router.post(
    "/gates/",
    response_model=GateResponse,
    status_code=201,
    dependencies=[Depends(RequirePermission("site_logistics.write"))],
)
async def create_gate(
    data: GateCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: SiteLogisticsService = Depends(_get_service),
) -> GateResponse:
    """Create a site access gate."""
    await verify_project_access(data.project_id, user_id, session)
    gate = await service.create_gate(data, user_id=user_id)
    return _gate_to_response(gate)


@router.get(
    "/gates/{gate_id}",
    response_model=GateResponse,
    dependencies=[Depends(RequirePermission("site_logistics.read"))],
)
async def get_gate(
    gate_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: SiteLogisticsService = Depends(_get_service),
) -> GateResponse:
    """Get a single gate."""
    gate = await service.get_gate(gate_id)
    await verify_project_access(gate.project_id, user_id, session)
    return _gate_to_response(gate)


@router.patch(
    "/gates/{gate_id}",
    response_model=GateResponse,
    dependencies=[Depends(RequirePermission("site_logistics.write"))],
)
async def update_gate(
    gate_id: uuid.UUID,
    data: GateUpdate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: SiteLogisticsService = Depends(_get_service),
) -> GateResponse:
    """Update a gate."""
    existing = await service.get_gate(gate_id)
    await verify_project_access(existing.project_id, user_id, session)
    gate = await service.update_gate(gate_id, data)
    return _gate_to_response(gate)


@router.delete(
    "/gates/{gate_id}",
    status_code=204,
    dependencies=[Depends(RequirePermission("site_logistics.write"))],
)
async def delete_gate(
    gate_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: SiteLogisticsService = Depends(_get_service),
) -> None:
    """Delete a gate."""
    existing = await service.get_gate(gate_id)
    await verify_project_access(existing.project_id, user_id, session)
    await service.delete_gate(gate_id)


# ── Laydown zones ──────────────────────────────────────────────────────────────


@router.get(
    "/laydown-zones",
    response_model=list[LaydownZoneResponse],
    dependencies=[Depends(RequirePermission("site_logistics.read"))],
    include_in_schema=False,
)
@router.get(
    "/laydown-zones/",
    response_model=list[LaydownZoneResponse],
    dependencies=[Depends(RequirePermission("site_logistics.read"))],
)
async def list_zones(
    user_id: CurrentUserId,
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    service: SiteLogisticsService = Depends(_get_service),
) -> list[LaydownZoneResponse]:
    """List material laydown zones for a project."""
    await verify_project_access(project_id, user_id, session)
    zones = await service.list_zones(project_id)
    return [_zone_to_response(z) for z in zones]


@router.post(
    "/laydown-zones/",
    response_model=LaydownZoneResponse,
    status_code=201,
    dependencies=[Depends(RequirePermission("site_logistics.write"))],
)
async def create_zone(
    data: LaydownZoneCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: SiteLogisticsService = Depends(_get_service),
) -> LaydownZoneResponse:
    """Create a laydown zone."""
    await verify_project_access(data.project_id, user_id, session)
    zone = await service.create_zone(data, user_id=user_id)
    return _zone_to_response(zone)


@router.get(
    "/laydown-zones/{zone_id}",
    response_model=LaydownZoneResponse,
    dependencies=[Depends(RequirePermission("site_logistics.read"))],
)
async def get_zone(
    zone_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: SiteLogisticsService = Depends(_get_service),
) -> LaydownZoneResponse:
    """Get a single laydown zone."""
    zone = await service.get_zone(zone_id)
    await verify_project_access(zone.project_id, user_id, session)
    return _zone_to_response(zone)


@router.patch(
    "/laydown-zones/{zone_id}",
    response_model=LaydownZoneResponse,
    dependencies=[Depends(RequirePermission("site_logistics.write"))],
)
async def update_zone(
    zone_id: uuid.UUID,
    data: LaydownZoneUpdate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: SiteLogisticsService = Depends(_get_service),
) -> LaydownZoneResponse:
    """Update a laydown zone."""
    existing = await service.get_zone(zone_id)
    await verify_project_access(existing.project_id, user_id, session)
    zone = await service.update_zone(zone_id, data)
    return _zone_to_response(zone)


@router.delete(
    "/laydown-zones/{zone_id}",
    status_code=204,
    dependencies=[Depends(RequirePermission("site_logistics.write"))],
)
async def delete_zone(
    zone_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: SiteLogisticsService = Depends(_get_service),
) -> None:
    """Delete a laydown zone."""
    existing = await service.get_zone(zone_id)
    await verify_project_access(existing.project_id, user_id, session)
    await service.delete_zone(zone_id)


# ── Deliveries ─────────────────────────────────────────────────────────────────


@router.get(
    "/deliveries",
    response_model=list[DeliveryResponse],
    dependencies=[Depends(RequirePermission("site_logistics.read"))],
    include_in_schema=False,
)
@router.get(
    "/deliveries/",
    response_model=list[DeliveryResponse],
    dependencies=[Depends(RequirePermission("site_logistics.read"))],
)
async def list_deliveries(
    user_id: CurrentUserId,
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    day: datetime | None = Query(default=None, description="Filter to deliveries whose window touches this day"),
    gate_id: uuid.UUID | None = Query(default=None),
    delivery_status: str | None = Query(default=None, alias="status"),
    service: SiteLogisticsService = Depends(_get_service),
) -> list[DeliveryResponse]:
    """List deliveries for a project, optionally filtered by day, gate and status."""
    await verify_project_access(project_id, user_id, session)
    deliveries = await service.list_deliveries(
        project_id,
        day=day,
        gate_id=gate_id,
        status_filter=delivery_status,
    )
    return [_delivery_to_response(d) for d in deliveries]


@router.post(
    "/deliveries/",
    response_model=DeliveryResponse,
    status_code=201,
    dependencies=[Depends(RequirePermission("site_logistics.write"))],
)
async def create_delivery(
    data: DeliveryCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: SiteLogisticsService = Depends(_get_service),
) -> DeliveryResponse:
    """Book an inbound delivery."""
    await verify_project_access(data.project_id, user_id, session)
    delivery = await service.create_delivery(data, user_id=user_id)
    return _delivery_to_response(delivery)


@router.get(
    "/deliveries/{delivery_id}",
    response_model=DeliveryResponse,
    dependencies=[Depends(RequirePermission("site_logistics.read"))],
)
async def get_delivery(
    delivery_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: SiteLogisticsService = Depends(_get_service),
) -> DeliveryResponse:
    """Get a single delivery."""
    delivery = await service.get_delivery(delivery_id)
    await verify_project_access(delivery.project_id, user_id, session)
    return _delivery_to_response(delivery)


@router.patch(
    "/deliveries/{delivery_id}",
    response_model=DeliveryResponse,
    dependencies=[Depends(RequirePermission("site_logistics.write"))],
)
async def update_delivery(
    delivery_id: uuid.UUID,
    data: DeliveryUpdate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: SiteLogisticsService = Depends(_get_service),
) -> DeliveryResponse:
    """Update a delivery booking."""
    existing = await service.get_delivery(delivery_id)
    await verify_project_access(existing.project_id, user_id, session)
    delivery = await service.update_delivery(delivery_id, data)
    return _delivery_to_response(delivery)


@router.delete(
    "/deliveries/{delivery_id}",
    status_code=204,
    dependencies=[Depends(RequirePermission("site_logistics.write"))],
)
async def delete_delivery(
    delivery_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: SiteLogisticsService = Depends(_get_service),
) -> None:
    """Delete a delivery booking."""
    existing = await service.get_delivery(delivery_id)
    await verify_project_access(existing.project_id, user_id, session)
    await service.delete_delivery(delivery_id)


@router.post(
    "/deliveries/{delivery_id}/approve/",
    response_model=DeliveryResponse,
    dependencies=[Depends(RequirePermission("site_logistics.approve"))],
)
async def approve_delivery(
    delivery_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    data: DeliveryDecisionRequest | None = None,
    service: SiteLogisticsService = Depends(_get_service),
) -> DeliveryResponse:
    """Approve a delivery, holding its gate slot (clash-checked)."""
    existing = await service.get_delivery(delivery_id)
    await verify_project_access(existing.project_id, user_id, session)
    delivery = await service.approve_delivery(
        delivery_id,
        reason=data.reason if data else None,
        user_id=user_id,
    )
    return _delivery_to_response(delivery)


@router.post(
    "/deliveries/{delivery_id}/reject/",
    response_model=DeliveryResponse,
    dependencies=[Depends(RequirePermission("site_logistics.approve"))],
)
async def reject_delivery(
    delivery_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    data: DeliveryDecisionRequest | None = None,
    service: SiteLogisticsService = Depends(_get_service),
) -> DeliveryResponse:
    """Reject a delivery, releasing its gate slot."""
    existing = await service.get_delivery(delivery_id)
    await verify_project_access(existing.project_id, user_id, session)
    delivery = await service.reject_delivery(
        delivery_id,
        reason=data.reason if data else None,
        user_id=user_id,
    )
    return _delivery_to_response(delivery)


# ── Stats ──────────────────────────────────────────────────────────────────────


@router.get(
    "/stats",
    response_model=SiteLogisticsStatsResponse,
    dependencies=[Depends(RequirePermission("site_logistics.read"))],
    include_in_schema=False,
)
@router.get(
    "/stats/",
    response_model=SiteLogisticsStatsResponse,
    dependencies=[Depends(RequirePermission("site_logistics.read"))],
)
async def site_logistics_stats(
    user_id: CurrentUserId,
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    service: SiteLogisticsService = Depends(_get_service),
) -> SiteLogisticsStatsResponse:
    """Aggregate delivery statistics for a project."""
    await verify_project_access(project_id, user_id, session)
    return await service.get_stats(project_id)
