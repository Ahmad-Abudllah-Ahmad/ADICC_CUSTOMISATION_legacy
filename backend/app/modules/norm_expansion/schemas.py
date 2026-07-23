# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Production-norm Pydantic schemas - request / response models.

Every numeric value (per-unit coefficients, quantities, expanded demand) is a
:class:`decimal.Decimal` on input and a decimal *string* on output, matching the
platform's Decimal-as-string wire contract. Returning a float would let a
JavaScript client lose precision on a large takeoff.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

# Upper bound for any single coefficient / quantity. 1e9 is far beyond any real
# productivity coefficient or takeoff quantity yet keeps every product finite.
_NUM_MAX = Decimal("1000000000")


def _serialise_decimal(v: Decimal | None) -> str | None:
    """Render a Decimal as a fixed-point string (None passes through)."""
    if v is None:
        return None
    if not isinstance(v, Decimal):
        try:
            v = Decimal(str(v))
        except (InvalidOperation, ValueError):
            return "0"
    if not v.is_finite():
        return "0"
    return format(v, "f")


# ── Materials ────────────────────────────────────────────────────────────────


class NormMaterialCreate(BaseModel):
    """Create / attach one material coefficient to a production norm."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=255)
    unit: str = Field(..., min_length=1, max_length=20)
    qty_per_unit: Decimal = Field(default=Decimal("0"), ge=0, le=_NUM_MAX)
    sort_order: int = Field(default=0, ge=0, le=100_000)


class NormMaterialResponse(BaseModel):
    """A material coefficient as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    norm_id: UUID
    name: str
    unit: str
    qty_per_unit: Decimal
    sort_order: int
    created_at: datetime
    updated_at: datetime

    @field_serializer("qty_per_unit")
    def _ser_qty(self, v: Decimal) -> str:
        return _serialise_decimal(v)  # type: ignore[return-value]


# ── Norms ────────────────────────────────────────────────────────────────────


class NormCreate(BaseModel):
    """Create a new production norm, optionally with its material coefficients."""

    model_config = ConfigDict(str_strip_whitespace=True)

    work_key: str = Field(..., min_length=1, max_length=120)
    name: str = Field(default="", max_length=255)
    unit: str = Field(..., min_length=1, max_length=20)
    category: str = Field(default="", max_length=100)
    labor_hours_per_unit: Decimal = Field(default=Decimal("0"), ge=0, le=_NUM_MAX)
    machine_hours_per_unit: Decimal = Field(default=Decimal("0"), ge=0, le=_NUM_MAX)
    notes: str = Field(default="", max_length=2000)
    is_active: bool = True
    materials: list[NormMaterialCreate] = Field(default_factory=list, max_length=200)


class NormUpdate(BaseModel):
    """Partial update for a production norm's scalar fields.

    Material coefficients are managed through the dedicated material
    sub-resource endpoints, not through this body.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    work_key: str | None = Field(default=None, min_length=1, max_length=120)
    name: str | None = Field(default=None, max_length=255)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    category: str | None = Field(default=None, max_length=100)
    labor_hours_per_unit: Decimal | None = Field(default=None, ge=0, le=_NUM_MAX)
    machine_hours_per_unit: Decimal | None = Field(default=None, ge=0, le=_NUM_MAX)
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class NormResponse(BaseModel):
    """A production norm (with its materials) as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    work_key: str
    name: str
    unit: str
    category: str
    labor_hours_per_unit: Decimal
    machine_hours_per_unit: Decimal
    notes: str
    is_active: bool
    materials: list[NormMaterialResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_serializer("labor_hours_per_unit", "machine_hours_per_unit")
    def _ser_coeff(self, v: Decimal) -> str:
        return _serialise_decimal(v)  # type: ignore[return-value]


# ── Expansion ────────────────────────────────────────────────────────────────


class ExpandRequest(BaseModel):
    """Expand a single work item's quantity into unpriced resource demand."""

    model_config = ConfigDict(str_strip_whitespace=True)

    work_key: str = Field(..., min_length=1, max_length=120)
    quantity: Decimal = Field(..., gt=0, le=_NUM_MAX)


class ExpandBatchRequest(BaseModel):
    """Expand several work items at once (e.g. a whole BOQ section)."""

    items: list[ExpandRequest] = Field(..., min_length=1, max_length=500)


class MaterialDemandResponse(BaseModel):
    """One expanded, unpriced material demand line."""

    name: str
    unit: str
    qty: Decimal

    @field_serializer("qty")
    def _ser_qty(self, v: Decimal) -> str:
        return _serialise_decimal(v)  # type: ignore[return-value]


class ExpansionResponse(BaseModel):
    """The unpriced resource demand behind a quantity of one work item."""

    work_key: str
    name: str
    unit: str
    quantity: Decimal
    labor_hours: Decimal
    machine_hours: Decimal
    materials: list[MaterialDemandResponse] = Field(default_factory=list)

    @field_serializer("quantity", "labor_hours", "machine_hours")
    def _ser_amounts(self, v: Decimal) -> str:
        return _serialise_decimal(v)  # type: ignore[return-value]


class ExpandBatchResponse(BaseModel):
    """Batch expansion result plus any work keys that had no matching norm."""

    results: list[ExpansionResponse] = Field(default_factory=list)
    unmatched: list[str] = Field(default_factory=list)


# ── Priced assembly build (slice 1a) ─────────────────────────────────────────


class BuildAssemblyRequest(BaseModel):
    """Build a priced assembly from a production norm.

    All fields are optional: with no labour-rate template the labour line is
    created unpriced and flagged (the estimator supplies a rate later); with no
    project the assembly is a library recipe rather than a project-scoped one.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    labor_rate_template_id: UUID | None = Field(
        default=None,
        description="Labour-rate template used to price labour-hours.",
    )
    machine_rate_template_id: UUID | None = Field(
        default=None,
        description="Rate template used as the equipment rate to price machine-hours.",
    )
    project_id: UUID | None = Field(
        default=None,
        description="Scope the built assembly to this project (omit for a library recipe).",
    )
    region: str | None = Field(
        default=None,
        max_length=64,
        description="Optional region hint biasing the material cost match.",
    )
    apply_waste: bool = Field(
        default=True,
        description=(
            "Gross each material from its net (installed) quantity up to the "
            "purchased (gross) quantity using the waste-factor library. Set false "
            "to price the net quantities with no waste allowance."
        ),
    )


class PricedComponentResponse(BaseModel):
    """One priced component of an assembly built from a norm.

    ``quantity`` is the per-unit coefficient (the NET / installed quantity for a
    material); ``unit_cost`` and ``total`` are money. For a material the waste
    fields describe the net -> gross allowance folded into ``total``:
    ``net_qty`` + ``waste_pct`` gives ``gross_qty``, and ``total`` is priced on
    the gross. They are ``None`` for labour / equipment (no waste applies).
    Every numeric field is emitted as a decimal string.
    """

    model_config = ConfigDict(from_attributes=True)

    resource_type: str | None = None
    description: str
    unit: str
    quantity: Decimal
    unit_cost: Decimal
    total: Decimal
    cost_item_id: UUID | None = None
    priced: bool = True
    unpriced_reason: str = ""
    net_qty: Decimal | None = None
    waste_pct: Decimal | None = None
    gross_qty: Decimal | None = None
    waste_matched: bool | None = None

    @field_serializer("quantity", "unit_cost", "total")
    def _ser_amounts(self, v: Decimal) -> str:
        return _serialise_decimal(v)  # type: ignore[return-value]

    @field_serializer("net_qty", "waste_pct", "gross_qty")
    def _ser_waste(self, v: Decimal | None) -> str | None:
        return _serialise_decimal(v)


class BuildAssemblyResponse(BaseModel):
    """The assembly created from a production norm, with its priced components.

    ``total_rate`` is the built-up unit rate (the sum of the component totals).
    ``unpriced`` lists the descriptions of any line that could not be priced so
    the UI can flag them for the estimator to resolve. ``waste_applied`` echoes
    whether the waste-factor library was used, and ``waste_unmatched`` lists the
    materials that were grossed up at pass-through (no library factor) so the
    estimator can add a factor for them.
    """

    id: UUID
    code: str
    name: str
    unit: str
    category: str
    currency: str
    total_rate: Decimal
    project_id: UUID | None = None
    is_template: bool
    work_key: str
    components: list[PricedComponentResponse] = Field(default_factory=list)
    unpriced: list[str] = Field(default_factory=list)
    waste_applied: bool = True
    waste_unmatched: list[str] = Field(default_factory=list)

    @field_serializer("total_rate")
    def _ser_total_rate(self, v: Decimal) -> str:
        return _serialise_decimal(v)  # type: ignore[return-value]
