# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pydantic schemas for the resource-depth slice (T3.1).

Pure (pydantic + stdlib) so it imports and unit-tests on the local runner.
Money fields are :class:`Decimal` and serialise to a JSON *string* via a
``field_serializer`` so large cents never round-trip through a binary float -
the platform-wide money discipline.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

RateType = Literal["cost", "billing", "overtime"]
CurveType = Literal["flat", "front_load", "back_load", "bell"]
UnitKind = Literal["labor", "equipment", "material", "other"]


def _ser_money(value: Decimal | None) -> str | None:
    """Serialise a money ``Decimal`` to a plain decimal string (or ``None``)."""
    if value is None:
        return None
    if not isinstance(value, Decimal):
        try:
            value = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return "0"
    if not value.is_finite():
        return "0"
    return format(value, "f")


# ── Rates ──────────────────────────────────────────────────────────────────


class RateCreate(BaseModel):
    """Create an effective-dated rate row for a resource."""

    model_config = ConfigDict(extra="forbid")

    resource_id: UUID
    rate: Decimal = Field(default=Decimal("0"), ge=0)
    rate_type: RateType = "cost"
    effective_from: date
    effective_to: date | None = None
    currency: str = Field(default="", max_length=3)


class RatePatch(BaseModel):
    """Partial update of a rate row."""

    model_config = ConfigDict(extra="forbid")

    rate: Decimal | None = Field(default=None, ge=0)
    rate_type: RateType | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    currency: str | None = Field(default=None, max_length=3)


class RateResponse(BaseModel):
    """An effective-dated rate row as returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    resource_id: UUID
    rate: Decimal
    rate_type: str
    effective_from: date
    effective_to: date | None
    currency: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("rate", when_used="json")
    def _ser_rate(self, v: Decimal) -> str | None:
        return _ser_money(v)


# ── Curves ─────────────────────────────────────────────────────────────────


class CurveUpsert(BaseModel):
    """Set (create or replace) an assignment's spreading curve."""

    model_config = ConfigDict(extra="forbid")

    curve_type: CurveType = "flat"
    manual_weights: list[float] = Field(default_factory=list)


class CurveResponse(BaseModel):
    """An assignment's spreading curve as returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    assignment_id: UUID
    curve_type: str
    manual_weights: list[float] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# ── Assignment units ───────────────────────────────────────────────────────


class AssignmentUnitsPatch(BaseModel):
    """Set the native-units demand + kind on an assignment.

    ``units`` is the resource-native demand (crew=3, excavator=1); ``None``
    leaves the demand to default to the percent allocation in the histogram.
    """

    model_config = ConfigDict(extra="forbid")

    units: float | None = Field(default=None, ge=0)
    unit_kind: UnitKind | None = None


class AssignmentUnitsResponse(BaseModel):
    """The native-units demand on an assignment after a units patch."""

    assignment_id: UUID
    units: float | None = None
    unit_kind: str = "labor"


# ── Histogram ──────────────────────────────────────────────────────────────


class HistogramBooking(BaseModel):
    """One assignment's contribution to a histogram bucket."""

    assignment_id: UUID
    project_id: UUID | None = None
    units: float
    unit_kind: str = "labor"


class HistogramCellResponse(BaseModel):
    """One bucket of a resource's time-phased histogram."""

    bucket_index: int
    start: datetime
    end: datetime
    label: str
    demand_units: float
    demand_cost: Decimal
    available: float | None
    capacity_unknown: bool
    over_allocated: bool
    bookings: list[HistogramBooking] = Field(default_factory=list)

    @field_serializer("demand_cost", when_used="json")
    def _ser_demand_cost(self, v: Decimal) -> str | None:
        return _ser_money(v)


class ResourceHistogramResponse(BaseModel):
    """A resource's time-phased demand-vs-availability-vs-cost histogram."""

    resource_id: UUID
    bucket: str
    capacity_units: float | None
    peak_demand: float
    over_allocated_buckets: int
    cells: list[HistogramCellResponse] = Field(default_factory=list)
