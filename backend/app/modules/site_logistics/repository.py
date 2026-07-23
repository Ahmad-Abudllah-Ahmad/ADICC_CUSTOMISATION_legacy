# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site Logistics data access layer.

Pure data access for gates, laydown zones and delivery bookings - no business
logic. All queries are project-scoped by the caller.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.site_logistics.models import DeliveryBooking, Gate, LaydownZone


class GateRepository:
    """Data access for Gate models."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, gate_id: uuid.UUID) -> Gate | None:
        """Get a gate by ID."""
        return await self.session.get(Gate, gate_id)

    async def list_for_project(self, project_id: uuid.UUID) -> list[Gate]:
        """List all gates for a project, ordered by name."""
        stmt = select(Gate).where(Gate.project_id == project_id).order_by(Gate.name.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, gate: Gate) -> Gate:
        """Insert a new gate."""
        self.session.add(gate)
        await self.session.flush()
        return gate

    async def update_fields(self, gate_id: uuid.UUID, **fields: object) -> None:
        """Update specific fields on a gate."""
        stmt = update(Gate).where(Gate.id == gate_id).values(**fields)
        await self.session.execute(stmt)
        await self.session.flush()
        self.session.expire_all()

    async def delete(self, gate: Gate) -> None:
        """Delete a gate."""
        await self.session.delete(gate)
        await self.session.flush()


class LaydownZoneRepository:
    """Data access for LaydownZone models."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, zone_id: uuid.UUID) -> LaydownZone | None:
        """Get a laydown zone by ID."""
        return await self.session.get(LaydownZone, zone_id)

    async def list_for_project(self, project_id: uuid.UUID) -> list[LaydownZone]:
        """List all laydown zones for a project, ordered by name."""
        stmt = select(LaydownZone).where(LaydownZone.project_id == project_id).order_by(LaydownZone.name.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, zone: LaydownZone) -> LaydownZone:
        """Insert a new laydown zone."""
        self.session.add(zone)
        await self.session.flush()
        return zone

    async def update_fields(self, zone_id: uuid.UUID, **fields: object) -> None:
        """Update specific fields on a laydown zone."""
        stmt = update(LaydownZone).where(LaydownZone.id == zone_id).values(**fields)
        await self.session.execute(stmt)
        await self.session.flush()
        self.session.expire_all()

    async def delete(self, zone: LaydownZone) -> None:
        """Delete a laydown zone."""
        await self.session.delete(zone)
        await self.session.flush()


class DeliveryRepository:
    """Data access for DeliveryBooking models."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, delivery_id: uuid.UUID) -> DeliveryBooking | None:
        """Get a delivery by ID."""
        return await self.session.get(DeliveryBooking, delivery_id)

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        *,
        day_start: datetime | None = None,
        day_end: datetime | None = None,
        gate_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> list[DeliveryBooking]:
        """List deliveries for a project, chronologically, with optional filters.

        When ``day_start`` / ``day_end`` are supplied, only deliveries whose
        window touches that half-open range ``[day_start, day_end)`` are
        returned (a delivery is "on" a day if its window overlaps the day).
        """
        stmt = select(DeliveryBooking).where(DeliveryBooking.project_id == project_id)
        if gate_id is not None:
            stmt = stmt.where(DeliveryBooking.gate_id == gate_id)
        if status is not None:
            stmt = stmt.where(DeliveryBooking.status == status)
        if day_start is not None and day_end is not None:
            # Window overlaps the day: starts before the day ends AND ends after
            # the day begins.
            stmt = stmt.where(
                DeliveryBooking.window_start < day_end,
                DeliveryBooking.window_end > day_start,
            )
        stmt = stmt.order_by(DeliveryBooking.window_start.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_approved_for_gate(
        self,
        gate_id: uuid.UUID,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> list[tuple[uuid.UUID, datetime, datetime]]:
        """Return ``(id, window_start, window_end)`` for approved gate deliveries.

        Used to detect clashes before approving another delivery. ``exclude_id``
        drops the delivery being (re)approved so it never clashes with itself.
        """
        stmt = select(
            DeliveryBooking.id,
            DeliveryBooking.window_start,
            DeliveryBooking.window_end,
        ).where(
            DeliveryBooking.gate_id == gate_id,
            DeliveryBooking.status == "approved",
        )
        if exclude_id is not None:
            stmt = stmt.where(DeliveryBooking.id != exclude_id)
        result = await self.session.execute(stmt)
        return [(row[0], row[1], row[2]) for row in result.all()]

    async def create(self, delivery: DeliveryBooking) -> DeliveryBooking:
        """Insert a new delivery booking."""
        self.session.add(delivery)
        await self.session.flush()
        return delivery

    async def update_fields(self, delivery_id: uuid.UUID, **fields: object) -> None:
        """Update specific fields on a delivery."""
        stmt = update(DeliveryBooking).where(DeliveryBooking.id == delivery_id).values(**fields)
        await self.session.execute(stmt)
        await self.session.flush()
        self.session.expire_all()

    async def delete(self, delivery: DeliveryBooking) -> None:
        """Delete a delivery."""
        await self.session.delete(delivery)
        await self.session.flush()

    async def status_counts(self, project_id: uuid.UUID) -> dict[str, int]:
        """Count deliveries grouped by status for a project."""
        stmt = (
            select(DeliveryBooking.status, func.count())
            .where(DeliveryBooking.project_id == project_id)
            .group_by(DeliveryBooking.status)
        )
        rows = (await self.session.execute(stmt)).all()
        return {row[0]: row[1] for row in rows}

    async def count_upcoming_approved(self, project_id: uuid.UUID, now: datetime) -> int:
        """Count approved deliveries whose window has not yet started."""
        stmt = (
            select(func.count())
            .select_from(DeliveryBooking)
            .where(
                DeliveryBooking.project_id == project_id,
                DeliveryBooking.status == "approved",
                DeliveryBooking.window_start >= now,
            )
        )
        return (await self.session.execute(stmt)).scalar_one()
