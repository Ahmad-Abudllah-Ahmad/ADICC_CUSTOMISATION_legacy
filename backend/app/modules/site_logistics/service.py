# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site Logistics service - business logic for gates, laydown zones and deliveries.

Stateless service layer. The delivery rules are enforced here so a booking that
breaks them is never persisted:

* a delivery window must fall inside its gate's open/close hours, and
* two *approved* deliveries on the same gate must not overlap in time.

Both checks reuse the pure helpers in ``validators.py`` and raise
``HTTPException(400)`` with a clear, user-facing message.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import event_bus
from app.core.json_merge import merge_metadata
from app.modules.site_logistics.events import (
    DELIVERY_APPROVED,
    DELIVERY_BOOKED,
    DELIVERY_REJECTED,
)
from app.modules.site_logistics.models import DeliveryBooking, Gate, LaydownZone
from app.modules.site_logistics.repository import (
    DeliveryRepository,
    GateRepository,
    LaydownZoneRepository,
)
from app.modules.site_logistics.schemas import (
    DeliveryCreate,
    DeliveryUpdate,
    GateCreate,
    GateUpdate,
    LaydownZoneCreate,
    LaydownZoneUpdate,
    SiteLogisticsStatsResponse,
)
from app.modules.site_logistics.validators import (
    delivery_within_gate_hours,
    find_first_overlap,
)

logger = logging.getLogger(__name__)

# Statuses a delivery can no longer be scheduled out of - the vehicle is on its
# way in or done, so approve/reject/window edits are refused.
_TERMINAL_ON_SITE = ("arrived", "completed")


def _ensure_aware(value: datetime) -> datetime:
    """Attach UTC to a naive datetime so windows are comparable and storable.

    Delivery boards run in one site timezone, so a naive wall-clock value from a
    ``datetime-local`` input is treated as UTC. This keeps overlap comparisons
    (stored tz-aware vs incoming) from raising and keeps PostgreSQL happy.
    """
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class SiteLogisticsService:
    """Business logic for site logistics operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.gate_repo = GateRepository(session)
        self.zone_repo = LaydownZoneRepository(session)
        self.delivery_repo = DeliveryRepository(session)

    # ── Gates ─────────────────────────────────────────────────────────────

    async def create_gate(self, data: GateCreate, user_id: str | None = None) -> Gate:
        """Create a site access gate."""
        gate = Gate(
            project_id=data.project_id,
            name=data.name,
            open_time=data.open_time,
            close_time=data.close_time,
            capacity_per_slot=data.capacity_per_slot,
            notes=data.notes,
            created_by=user_id,
            metadata_=data.metadata,
        )
        gate = await self.gate_repo.create(gate)
        await self.session.commit()
        logger.info("Site gate created: %s for project %s", data.name, data.project_id)
        return gate

    async def get_gate(self, gate_id: uuid.UUID) -> Gate:
        """Get a gate by ID. Raises 404 if not found."""
        gate = await self.gate_repo.get_by_id(gate_id)
        if gate is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gate not found")
        return gate

    async def list_gates(self, project_id: uuid.UUID) -> list[Gate]:
        """List gates for a project."""
        return await self.gate_repo.list_for_project(project_id)

    async def update_gate(self, gate_id: uuid.UUID, data: GateUpdate) -> Gate:
        """Update a gate. Re-validates that close stays after open."""
        gate = await self.get_gate(gate_id)
        fields = self._merge_metadata_fields(data.model_dump(exclude_unset=True), gate)
        if not fields:
            return gate

        open_time = fields.get("open_time", gate.open_time)
        close_time = fields.get("close_time", gate.close_time)
        if close_time <= open_time:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="close_time must be later than open_time",
            )

        await self.gate_repo.update_fields(gate_id, **fields)
        await self.session.refresh(gate)
        await self.session.commit()
        return gate

    async def delete_gate(self, gate_id: uuid.UUID) -> None:
        """Delete a gate. Deliveries keep their history (gate_id is set null)."""
        gate = await self.get_gate(gate_id)
        await self.gate_repo.delete(gate)
        await self.session.commit()
        logger.info("Site gate deleted: %s", gate_id)

    # ── Laydown zones ─────────────────────────────────────────────────────

    async def create_zone(self, data: LaydownZoneCreate, user_id: str | None = None) -> LaydownZone:
        """Create a laydown zone."""
        zone = LaydownZone(
            project_id=data.project_id,
            name=data.name,
            capacity_desc=data.capacity_desc,
            usage_note=data.usage_note,
            created_by=user_id,
            metadata_=data.metadata,
        )
        zone = await self.zone_repo.create(zone)
        await self.session.commit()
        logger.info("Laydown zone created: %s for project %s", data.name, data.project_id)
        return zone

    async def get_zone(self, zone_id: uuid.UUID) -> LaydownZone:
        """Get a laydown zone by ID. Raises 404 if not found."""
        zone = await self.zone_repo.get_by_id(zone_id)
        if zone is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Laydown zone not found")
        return zone

    async def list_zones(self, project_id: uuid.UUID) -> list[LaydownZone]:
        """List laydown zones for a project."""
        return await self.zone_repo.list_for_project(project_id)

    async def update_zone(self, zone_id: uuid.UUID, data: LaydownZoneUpdate) -> LaydownZone:
        """Update a laydown zone."""
        zone = await self.get_zone(zone_id)
        fields = self._merge_metadata_fields(data.model_dump(exclude_unset=True), zone)
        if not fields:
            return zone
        await self.zone_repo.update_fields(zone_id, **fields)
        await self.session.refresh(zone)
        await self.session.commit()
        return zone

    async def delete_zone(self, zone_id: uuid.UUID) -> None:
        """Delete a laydown zone."""
        zone = await self.get_zone(zone_id)
        await self.zone_repo.delete(zone)
        await self.session.commit()
        logger.info("Laydown zone deleted: %s", zone_id)

    # ── Deliveries ────────────────────────────────────────────────────────

    async def create_delivery(self, data: DeliveryCreate, user_id: str | None = None) -> DeliveryBooking:
        """Book an inbound delivery, validating window and gate rules first."""
        window_start = _ensure_aware(data.window_start)
        window_end = _ensure_aware(data.window_end)

        if data.gate_id is not None:
            gate = await self._load_project_gate(data.gate_id, data.project_id)
            self._assert_within_gate_hours(gate, window_start, window_end)
            if data.status == "approved":
                await self._assert_no_overlap(data.gate_id, window_start, window_end, exclude_id=None)

        delivery = DeliveryBooking(
            project_id=data.project_id,
            gate_id=data.gate_id,
            supplier_name=data.supplier_name,
            contact_name=data.contact_name,
            contact_phone=data.contact_phone,
            vehicle_type=data.vehicle_type,
            materials_desc=data.materials_desc,
            window_start=window_start,
            window_end=window_end,
            status=data.status,
            po_ref=data.po_ref,
            notes=data.notes,
            created_by=user_id,
            metadata_=data.metadata,
        )
        delivery = await self.delivery_repo.create(delivery)
        await self.session.refresh(delivery)
        await self.session.commit()

        logger.info(
            "Delivery booked: %s at gate %s [%s] for project %s",
            data.supplier_name,
            data.gate_id,
            data.status,
            data.project_id,
        )
        self._emit(DELIVERY_BOOKED, delivery, user_id)
        if delivery.status == "approved":
            self._emit(DELIVERY_APPROVED, delivery, user_id)
        return delivery

    async def get_delivery(self, delivery_id: uuid.UUID) -> DeliveryBooking:
        """Get a delivery by ID. Raises 404 if not found."""
        delivery = await self.delivery_repo.get_by_id(delivery_id)
        if delivery is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")
        return delivery

    async def list_deliveries(
        self,
        project_id: uuid.UUID,
        *,
        day: datetime | None = None,
        gate_id: uuid.UUID | None = None,
        status_filter: str | None = None,
    ) -> list[DeliveryBooking]:
        """List deliveries for a project, optionally filtered by day/gate/status."""
        day_start: datetime | None = None
        day_end: datetime | None = None
        if day is not None:
            day = _ensure_aware(day)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start.replace(hour=23, minute=59, second=59, microsecond=999999)
        return await self.delivery_repo.list_for_project(
            project_id,
            day_start=day_start,
            day_end=day_end,
            gate_id=gate_id,
            status=status_filter,
        )

    async def update_delivery(self, delivery_id: uuid.UUID, data: DeliveryUpdate) -> DeliveryBooking:
        """Update a delivery, re-validating window and gate rules on the result."""
        delivery = await self.get_delivery(delivery_id)
        previous_status = delivery.status
        fields = self._merge_metadata_fields(data.model_dump(exclude_unset=True), delivery)
        if not fields:
            return delivery

        if "window_start" in fields:
            fields["window_start"] = _ensure_aware(fields["window_start"])
        if "window_end" in fields:
            fields["window_end"] = _ensure_aware(fields["window_end"])

        new_start: datetime = fields.get("window_start", delivery.window_start)
        new_end: datetime = fields.get("window_end", delivery.window_end)
        new_gate_id = fields.get("gate_id", delivery.gate_id)
        new_status = fields.get("status", delivery.status)

        if new_end <= new_start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="window_end must be after window_start",
            )
        if new_gate_id is not None:
            gate = await self._load_project_gate(new_gate_id, delivery.project_id)
            self._assert_within_gate_hours(gate, new_start, new_end)
            if new_status == "approved":
                await self._assert_no_overlap(new_gate_id, new_start, new_end, exclude_id=delivery_id)

        await self.delivery_repo.update_fields(delivery_id, **fields)
        await self.session.refresh(delivery)
        await self.session.commit()

        if new_status == "approved" and previous_status != "approved":
            self._emit(DELIVERY_APPROVED, delivery, delivery.created_by)
        logger.info("Delivery updated: %s (fields=%s)", delivery_id, list(fields.keys()))
        return delivery

    async def delete_delivery(self, delivery_id: uuid.UUID) -> None:
        """Delete a delivery booking."""
        delivery = await self.get_delivery(delivery_id)
        await self.delivery_repo.delete(delivery)
        logger.info("Delivery deleted: %s", delivery_id)

    async def approve_delivery(
        self,
        delivery_id: uuid.UUID,
        *,
        reason: str | None = None,
        user_id: str | None = None,
    ) -> DeliveryBooking:
        """Approve a delivery: requested/rejected -> approved, clash-checked."""
        delivery = await self.get_delivery(delivery_id)
        if delivery.status == "approved":
            return delivery
        if delivery.status in _TERMINAL_ON_SITE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot approve a delivery that has already {delivery.status}",
            )

        # Re-check window + gate hours and clash at decision time - a gate's
        # hours or a rival booking may have changed since it was requested.
        if delivery.gate_id is not None:
            gate = await self._load_project_gate(delivery.gate_id, delivery.project_id)
            self._assert_within_gate_hours(gate, delivery.window_start, delivery.window_end)
            await self._assert_no_overlap(
                delivery.gate_id,
                delivery.window_start,
                delivery.window_end,
                exclude_id=delivery_id,
            )

        fields = self._decision_fields(delivery, "approved", reason, user_id)
        await self.delivery_repo.update_fields(delivery_id, **fields)
        await self.session.refresh(delivery)
        await self.session.commit()
        logger.info("Delivery approved: %s by %s", delivery_id, user_id)
        self._emit(DELIVERY_APPROVED, delivery, user_id)
        return delivery

    async def reject_delivery(
        self,
        delivery_id: uuid.UUID,
        *,
        reason: str | None = None,
        user_id: str | None = None,
    ) -> DeliveryBooking:
        """Reject a delivery: requested/approved -> rejected, releasing its slot."""
        delivery = await self.get_delivery(delivery_id)
        if delivery.status in _TERMINAL_ON_SITE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot reject a delivery that has already {delivery.status}",
            )
        if delivery.status == "rejected":
            return delivery

        fields = self._decision_fields(delivery, "rejected", reason, user_id)
        await self.delivery_repo.update_fields(delivery_id, **fields)
        await self.session.refresh(delivery)
        await self.session.commit()
        logger.info("Delivery rejected: %s by %s", delivery_id, user_id)
        self._emit(DELIVERY_REJECTED, delivery, user_id)
        return delivery

    # ── Stats ─────────────────────────────────────────────────────────────

    async def get_stats(self, project_id: uuid.UUID) -> SiteLogisticsStatsResponse:
        """Return aggregate delivery statistics for a project."""
        by_status = await self.delivery_repo.status_counts(project_id)
        gates = await self.gate_repo.list_for_project(project_id)
        zones = await self.zone_repo.list_for_project(project_id)
        upcoming = await self.delivery_repo.count_upcoming_approved(project_id, datetime.now(UTC))
        return SiteLogisticsStatsResponse(
            total_deliveries=sum(by_status.values()),
            by_status=by_status,
            gate_count=len(gates),
            laydown_zone_count=len(zones),
            upcoming_approved=upcoming,
        )

    # ── Internal helpers ──────────────────────────────────────────────────

    async def _load_project_gate(self, gate_id: uuid.UUID, project_id: uuid.UUID) -> Gate:
        """Load a gate and confirm it belongs to the delivery's project."""
        gate = await self.gate_repo.get_by_id(gate_id)
        if gate is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gate not found")
        if gate.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Gate belongs to a different project",
            )
        return gate

    @staticmethod
    def _assert_within_gate_hours(gate: Gate, window_start: datetime, window_end: datetime) -> None:
        """Raise 400 when the window falls outside the gate's operating hours."""
        ok, reason = delivery_within_gate_hours(gate.open_time, gate.close_time, window_start, window_end)
        if not ok:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    async def _assert_no_overlap(
        self,
        gate_id: uuid.UUID,
        window_start: datetime,
        window_end: datetime,
        *,
        exclude_id: uuid.UUID | None,
    ) -> None:
        """Raise 400 when an approved delivery already holds an overlapping slot."""
        existing = await self.delivery_repo.list_approved_for_gate(gate_id, exclude_id=exclude_id)
        clash = find_first_overlap(window_start, window_end, [(s, e) for _id, s, e in existing])
        if clash is not None:
            clash_start, clash_end = clash
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "This window clashes with an approved delivery from "
                    f"{clash_start:%Y-%m-%d %H:%M} to {clash_end:%H:%M} on this gate"
                ),
            )

    @staticmethod
    def _merge_metadata_fields(fields: dict[str, Any], entity: object) -> dict[str, Any]:
        """Rename the incoming ``metadata`` key to ``metadata_`` and merge it."""
        if "metadata" in fields:
            incoming = fields.pop("metadata")
            fields["metadata_"] = (
                merge_metadata(getattr(entity, "metadata_", None), incoming) if isinstance(incoming, dict) else incoming
            )
        return fields

    @staticmethod
    def _decision_fields(
        delivery: DeliveryBooking,
        decision: str,
        reason: str | None,
        user_id: str | None,
    ) -> dict[str, Any]:
        """Build the update fields for an approve/reject, recording an audit note."""
        md = dict(delivery.metadata_ or {})
        md["last_decision"] = {
            "decision": decision,
            "by": user_id,
            "at": datetime.now(UTC).isoformat(),
            "reason": reason,
        }
        return {"status": decision, "metadata_": md}

    @staticmethod
    def _emit(topic: str, delivery: DeliveryBooking, user_id: str | None) -> None:
        """Publish a delivery lifecycle event for cross-module subscribers."""
        event_bus.publish_detached(
            topic,
            data={
                "project_id": str(delivery.project_id),
                "delivery_id": str(delivery.id),
                "gate_id": str(delivery.gate_id) if delivery.gate_id else None,
                "supplier_name": delivery.supplier_name,
                "window_start": delivery.window_start.isoformat() if delivery.window_start else None,
                "window_end": delivery.window_end.isoformat() if delivery.window_end else None,
                "status": delivery.status,
                "user_id": user_id,
            },
            source_module="site_logistics",
        )
