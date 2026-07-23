# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site Logistics Pydantic schemas - request/response models.

Covers gates, laydown zones and delivery bookings following the create /
update / response split used across the platform.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.site_logistics.models import DELIVERY_STATUSES

# "HH:MM" 24-hour clock, e.g. 07:00 / 18:30.
_HHMM_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
# Delivery status enum built from the single source of truth in models.py.
_STATUS_PATTERN = r"^(" + "|".join(DELIVERY_STATUSES) + r")$"


# ── Gate ───────────────────────────────────────────────────────────────────


class GateCreate(BaseModel):
    """Create a site access gate."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    open_time: str = Field(default="07:00", pattern=_HHMM_PATTERN)
    close_time: str = Field(default="18:00", pattern=_HHMM_PATTERN)
    capacity_per_slot: int = Field(default=1, ge=1, le=100)
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_hours(self) -> "GateCreate":
        if self.close_time <= self.open_time:
            raise ValueError("close_time must be later than open_time")
        return self


class GateUpdate(BaseModel):
    """Partial update for a gate."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    open_time: str | None = Field(default=None, pattern=_HHMM_PATTERN)
    close_time: str | None = Field(default=None, pattern=_HHMM_PATTERN)
    capacity_per_slot: int | None = Field(default=None, ge=1, le=100)
    notes: str | None = None
    metadata: dict[str, Any] | None = None


class GateResponse(BaseModel):
    """A gate returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    name: str
    open_time: str
    close_time: str
    capacity_per_slot: int
    notes: str | None = None
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── Laydown zone ───────────────────────────────────────────────────────────


class LaydownZoneCreate(BaseModel):
    """Create a material laydown zone."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    capacity_desc: str | None = Field(default=None, max_length=255)
    usage_note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LaydownZoneUpdate(BaseModel):
    """Partial update for a laydown zone."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    capacity_desc: str | None = Field(default=None, max_length=255)
    usage_note: str | None = None
    metadata: dict[str, Any] | None = None


class LaydownZoneResponse(BaseModel):
    """A laydown zone returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    name: str
    capacity_desc: str | None = None
    usage_note: str | None = None
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── Delivery booking ───────────────────────────────────────────────────────


class DeliveryCreate(BaseModel):
    """Book an inbound delivery."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    gate_id: UUID | None = None
    supplier_name: str = Field(..., min_length=1, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=50)
    vehicle_type: str | None = Field(default=None, max_length=120)
    materials_desc: str | None = None
    window_start: datetime
    window_end: datetime
    status: str = Field(default="requested", pattern=_STATUS_PATTERN)
    po_ref: str | None = Field(default=None, max_length=120)
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_window(self) -> "DeliveryCreate":
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        return self


class DeliveryUpdate(BaseModel):
    """Partial update for a delivery booking."""

    model_config = ConfigDict(str_strip_whitespace=True)

    gate_id: UUID | None = None
    supplier_name: str | None = Field(default=None, min_length=1, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=50)
    vehicle_type: str | None = Field(default=None, max_length=120)
    materials_desc: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    status: str | None = Field(default=None, pattern=_STATUS_PATTERN)
    po_ref: str | None = Field(default=None, max_length=120)
    notes: str | None = None
    metadata: dict[str, Any] | None = None


class DeliveryDecisionRequest(BaseModel):
    """Approve or reject a delivery, with an optional reason for the audit note."""

    model_config = ConfigDict(str_strip_whitespace=True)

    reason: str | None = Field(default=None, max_length=500)


class DeliveryResponse(BaseModel):
    """A delivery booking returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    gate_id: UUID | None = None
    supplier_name: str
    contact_name: str | None = None
    contact_phone: str | None = None
    vehicle_type: str | None = None
    materials_desc: str | None = None
    window_start: datetime
    window_end: datetime
    status: str = "requested"
    po_ref: str | None = None
    notes: str | None = None
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── Stats ──────────────────────────────────────────────────────────────────


class SiteLogisticsStatsResponse(BaseModel):
    """Aggregate delivery statistics for a project."""

    total_deliveries: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    gate_count: int = 0
    laydown_zone_count: int = 0
    upcoming_approved: int = 0
