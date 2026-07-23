# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site Logistics & Delivery ORM models.

Tables:
    oe_site_logistics_gate          - site access gates with daily hours + slot capacity
    oe_site_logistics_laydown_zone  - material laydown / storage areas on site
    oe_site_logistics_delivery      - inbound delivery bookings scheduled against a gate
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base

# Canonical delivery-booking lifecycle. Kept here so schemas (validation
# pattern) and the service (transition rules) share one source of truth.
DELIVERY_STATUSES: tuple[str, ...] = (
    "requested",  # booked by requester, awaiting gate approval
    "approved",  # scheduled - holds its slot on the gate
    "rejected",  # declined (clash, wrong window, no capacity)
    "arrived",  # vehicle checked in at the gate
    "completed",  # unloaded and released
)


class Gate(Base):
    """A site access gate with daily operating hours and per-slot capacity."""

    __tablename__ = "oe_site_logistics_gate"

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Daily operating window as "HH:MM" 24h strings - DB-agnostic and trivial to
    # compare against a delivery window's time-of-day (see validators.py).
    open_time: Mapped[str] = mapped_column(String(5), nullable=False, default="07:00")
    close_time: Mapped[str] = mapped_column(String(5), nullable=False, default="18:00")
    # How many vehicles the gate can handle per booking slot; drives capacity
    # planning and future slotting. Never zero - a gate with no capacity cannot
    # take deliveries.
    capacity_per_slot: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<Gate {self.name} ({self.open_time}-{self.close_time})>"


class LaydownZone(Base):
    """A material laydown / storage area on site."""

    __tablename__ = "oe_site_logistics_laydown_zone"

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Free-text capacity (e.g. "200 m2 / 40 t") rather than a modelled number:
    # laydown capacity on site is judged, not metered.
    capacity_desc: Mapped[str | None] = mapped_column(String(255), nullable=True)
    usage_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<LaydownZone {self.name}>"


class DeliveryBooking(Base):
    """An inbound delivery booked into a time window against a site gate."""

    __tablename__ = "oe_site_logistics_delivery"

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable: a delivery can be logged before a gate is assigned. SET NULL on
    # gate delete so removing a gate never destroys its delivery history.
    gate_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_site_logistics_gate.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    supplier_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vehicle_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    materials_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested", index=True)
    po_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<DeliveryBooking {self.supplier_name} {self.window_start:%Y-%m-%d %H:%M} ({self.status})>"
