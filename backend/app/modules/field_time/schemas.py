# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Field Time Pydantic schemas - request / response models.

Hours are ``Decimal`` in and out but serialised to a string in JSON (the
platform-wide "money / quantity as string" convention) so a large or high
precision value never loses digits through a JavaScript ``Number``.
"""

from __future__ import annotations

# ``date`` is aliased so a Pydantic field literally named ``date`` (with a
# default) cannot shadow the type token in its own annotation, which would fail
# model construction under ``from __future__ import annotations``.
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

# Status values a timesheet can carry.
STATUS_PATTERN = r"^(draft|submitted|approved|reversed)$"


def _money_str(value: Decimal | None) -> str | None:
    """Render a Decimal as a plain, JS-safe decimal string (None passes through)."""
    if value is None:
        return None
    return format(value, "f")


# ── Line ─────────────────────────────────────────────────────────────────────


class FieldTimesheetLineCreate(BaseModel):
    """Create one labour or plant line on a timesheet.

    Exactly one of ``resource_id`` (labour) / ``equipment_id`` (plant) must be
    set - the service and a DB CHECK constraint both enforce it.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    resource_id: UUID | None = None
    equipment_id: UUID | None = None
    hours: Decimal = Field(default=Decimal("0"), ge=0, le=100000, max_digits=18, decimal_places=4)
    cost_code: str = Field(default="", max_length=100)
    wbs: str | None = Field(default=None, max_length=100)
    is_daywork: bool = False
    variation_id: UUID | None = None
    note: str | None = Field(default=None, max_length=2000)


class FieldTimesheetLineUpdate(BaseModel):
    """Partial update of a single line (draft timesheets only)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    resource_id: UUID | None = None
    equipment_id: UUID | None = None
    hours: Decimal | None = Field(default=None, ge=0, le=100000, max_digits=18, decimal_places=4)
    cost_code: str | None = Field(default=None, max_length=100)
    wbs: str | None = Field(default=None, max_length=100)
    is_daywork: bool | None = None
    variation_id: UUID | None = None
    note: str | None = Field(default=None, max_length=2000)


class FieldTimesheetLineResponse(BaseModel):
    """A timesheet line returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    timesheet_id: UUID
    resource_id: UUID | None = None
    equipment_id: UUID | None = None
    hours: Decimal = Decimal("0")
    cost_code: str = ""
    wbs: str | None = None
    is_daywork: bool = False
    variation_id: UUID | None = None
    daywork_sheet_id: UUID | None = None
    note: str | None = None
    # Derived, read-only: "labour" or "plant".
    kind: str = "labour"
    created_at: datetime
    updated_at: datetime

    @field_serializer("hours", when_used="json")
    @classmethod
    def _ser_hours(cls, value: Decimal) -> str:
        return _money_str(value) or "0"


# ── Timesheet ────────────────────────────────────────────────────────────────


class FieldTimesheetCreate(BaseModel):
    """Create a new (draft) field timesheet, optionally with its lines."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    project_id: UUID
    date: date_type
    note: str | None = Field(default=None, max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    lines: list[FieldTimesheetLineCreate] = Field(default_factory=list, max_length=1000)


class FieldTimesheetUpdate(BaseModel):
    """Partial update of a draft timesheet's header fields."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    date: date_type | None = None
    note: str | None = Field(default=None, max_length=5000)
    metadata: dict[str, Any] | None = None


class FieldTimesheetResponse(BaseModel):
    """A field timesheet returned from the API, with its lines and hours rollup."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    reference: str = ""
    date: date_type
    status: str = "draft"
    submitted_by: UUID | None = None
    submitted_at: datetime | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    reverses_id: UUID | None = None
    note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    lines: list[FieldTimesheetLineResponse] = Field(default_factory=list)
    # Hours rollup (strings): the sum of this timesheet's line hours, split by
    # whether each line books a worker (labour) or a machine (plant). These are
    # totals of the hours as entered, not a cost figure.
    labour_hours: str = "0"
    plant_hours: str = "0"
    created_at: datetime
    updated_at: datetime


# ── Reverse ──────────────────────────────────────────────────────────────────


class ReverseTimesheetRequest(BaseModel):
    """Body for reversing an approved timesheet."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    note: str | None = Field(default=None, max_length=5000, description="Reason for the reversal")


# ── Validation ───────────────────────────────────────────────────────────────


class ValidationResultOut(BaseModel):
    """One validation finding for the traffic-light dashboard."""

    rule_id: str
    rule_name: str
    severity: str
    category: str
    passed: bool
    message: str
    element_ref: str | None = None
    suggestion: str | None = None


class ValidationReportOut(BaseModel):
    """Aggregated validation outcome for a timesheet."""

    status: str
    score: float | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    results: list[ValidationResultOut] = Field(default_factory=list)


# ── Cost-code suggestion (AI-augmented, human-confirmed) ─────────────────────


class SuggestCostCodeRequest(BaseModel):
    """Ask for ranked cost-code suggestions for a free-text line description."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    text: str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=25)


class CostCodeSuggestionOut(BaseModel):
    """A ranked, confidence-scored cost-code suggestion the user must confirm."""

    code: str
    label: str
    confidence: float


class SuggestCostCodeResponse(BaseModel):
    """Suggestions plus an explicit reminder that nothing was applied."""

    suggestions: list[CostCodeSuggestionOut] = Field(default_factory=list)
    applied: bool = False


# ── Summary ──────────────────────────────────────────────────────────────────


class FieldTimeSummary(BaseModel):
    """Project-level rollup of field timesheets.

    Hour totals are strings (the money / quantity convention) and cover only
    live approved timesheets. ``overtime_hours`` is the portion of labour hours
    above the project's daily overtime threshold, summed per worker per day; it
    is ``"0"`` for any project that does not configure overtime.
    """

    total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    labour_hours: str = "0"
    plant_hours: str = "0"
    overtime_hours: str = "0"
