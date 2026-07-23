# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Defects-liability Pydantic v2 schemas (request / response models).

Calendar dates cross the wire as ISO-8601 strings (``YYYY-MM-DD``) and are typed
as :class:`datetime.date` on create/update so Pydantic parses and validates them.
The register and readiness responses report their derived percentages
(``overall_health_score``, per-subcontractor ``health_score``) as plain decimal
strings (``None`` meaning "undefined", e.g. an empty register) via field
serialisers, so no float rounding is introduced at the API edge, mirroring the
money-as-string convention used across the platform. Other derived views (counts,
expiring / expired / overdue / ready lists) come straight from the dicts produced
by the pure :mod:`app.modules.defects_liability.register` core.

The warranty-type / status / defect-status / severity vocabularies are the single
source of truth in :mod:`app.modules.defects_liability.register`; the ``Literal``
types below enumerate the same values so an out-of-vocabulary value is rejected at
the edge (422).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

# Vocabularies (kept in lock-step with app.modules.defects_liability.register).
WarrantyTypeLiteral = Literal[
    "workmanship",
    "manufacturer",
    "latent_defect",
    "extended",
    "other",
]
WarrantyStatusLiteral = Literal[
    "in_dlp",
    "expiring",
    "expired",
    "closed",
    "on_hold",
]
DefectStatusLiteral = Literal[
    "open",
    "rectifying",
    "rectified",
    "rejected",
    "closed",
]
DefectSeverityLiteral = Literal["minor", "major", "critical"]


def _serialise_pct(v: Decimal | None) -> str | None:
    """Render a percentage Decimal as a plain decimal string for JSON.

    Returns ``None`` when the value is ``None`` (undefined), ``"0"`` for a
    non-finite or unparseable value, and otherwise the value formatted with
    :func:`format` (``"f"``) so no scientific notation or float rounding leaks
    into the response.
    """
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


# -- Warranty / DLP entry ----------------------------------------------------


class WarrantyCreate(BaseModel):
    """Create a warranty / DLP entry on a project."""

    model_config = ConfigDict(str_strip_whitespace=True)

    reference: str = Field(..., min_length=1, max_length=40)
    title: str = Field(..., min_length=1, max_length=255)
    element_description: str | None = Field(default=None, max_length=20000)
    subcontractor_id: UUID | None = None
    subcontractor_name: str | None = Field(default=None, max_length=255)
    work_package: str | None = Field(default=None, max_length=120)
    warranty_type: WarrantyTypeLiteral | None = None
    handover_date: date | None = None
    warranty_start_date: date | None = None
    warranty_months: int | None = Field(default=None, ge=0, le=1200)
    warranty_end_date: date | None = None
    dlp_end_date: date | None = None
    status: WarrantyStatusLiteral = "in_dlp"
    retention_release_date: date | None = None
    contract_id: UUID | None = None
    document_id: UUID | None = None
    sort_order: int = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=20000)


class WarrantyUpdate(BaseModel):
    """Patch a warranty / DLP entry. Only fields provided are changed.

    A field explicitly set to ``null`` clears it; an omitted field is left
    untouched (the service applies ``exclude_unset``).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    reference: str | None = Field(default=None, min_length=1, max_length=40)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    element_description: str | None = Field(default=None, max_length=20000)
    subcontractor_id: UUID | None = None
    subcontractor_name: str | None = Field(default=None, max_length=255)
    work_package: str | None = Field(default=None, max_length=120)
    warranty_type: WarrantyTypeLiteral | None = None
    handover_date: date | None = None
    warranty_start_date: date | None = None
    warranty_months: int | None = Field(default=None, ge=0, le=1200)
    warranty_end_date: date | None = None
    dlp_end_date: date | None = None
    status: WarrantyStatusLiteral | None = None
    retention_release_date: date | None = None
    contract_id: UUID | None = None
    document_id: UUID | None = None
    sort_order: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=20000)


class WarrantyResponse(BaseModel):
    """A warranty / DLP entry returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    reference: str
    title: str
    element_description: str | None = None
    subcontractor_id: UUID | None = None
    subcontractor_name: str | None = None
    work_package: str | None = None
    warranty_type: str | None = None
    handover_date: date | None = None
    warranty_start_date: date | None = None
    warranty_months: int | None = None
    warranty_end_date: date | None = None
    dlp_end_date: date | None = None
    status: str
    retention_release_date: date | None = None
    contract_id: UUID | None = None
    document_id: UUID | None = None
    sort_order: int
    notes: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


# -- Defect notice -----------------------------------------------------------


class DefectCreate(BaseModel):
    """Raise a defect notice against a warranty / DLP entry.

    The warranty and project are taken from the path, never the body, so a defect
    can only ever be attached to the warranty named in the URL.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    reference: str = Field(..., min_length=1, max_length=40)
    description: str = Field(..., min_length=1, max_length=20000)
    severity: DefectSeverityLiteral | None = None
    raised_date: date | None = None
    due_date: date | None = None
    status: DefectStatusLiteral = "open"
    rectified_date: date | None = None
    responsible_party: str | None = Field(default=None, max_length=255)
    punchlist_id: str | None = Field(default=None, max_length=36)
    ncr_id: str | None = Field(default=None, max_length=36)


class DefectUpdate(BaseModel):
    """Patch (or close) a defect notice. Only fields provided are changed."""

    model_config = ConfigDict(str_strip_whitespace=True)

    reference: str | None = Field(default=None, min_length=1, max_length=40)
    description: str | None = Field(default=None, min_length=1, max_length=20000)
    severity: DefectSeverityLiteral | None = None
    raised_date: date | None = None
    due_date: date | None = None
    status: DefectStatusLiteral | None = None
    rectified_date: date | None = None
    responsible_party: str | None = Field(default=None, max_length=255)
    punchlist_id: str | None = Field(default=None, max_length=36)
    ncr_id: str | None = Field(default=None, max_length=36)


class DefectResponse(BaseModel):
    """A defect notice returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    warranty_id: UUID
    reference: str
    description: str
    severity: str | None = None
    raised_date: date | None = None
    due_date: date | None = None
    status: str
    rectified_date: date | None = None
    responsible_party: str | None = None
    punchlist_id: str | None = None
    ncr_id: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


# -- Derived register views --------------------------------------------------


class WarrantyRef(BaseModel):
    """A lightweight reference to an entry, used in expiring / expired / ready lists."""

    warranty_id: str | None = None
    reference: str
    title: str
    status: str
    subcontractor_name: str | None = None
    work_package: str | None = None
    warranty_type: str | None = None
    dlp_end_date: str | None = None
    warranty_end_date: str | None = None
    open_defect_count: int = 0
    retention_release_ready: bool = False


class OverdueDefectRef(BaseModel):
    """One overdue defect, carrying its owning warranty's identity."""

    warranty_id: str | None = None
    warranty_reference: str
    title: str
    severity: str | None = None
    status: str
    due_date: str | None = None


class SubcontractorDlpHealthResponse(BaseModel):
    """Post-handover DLP health rollup for one subcontractor."""

    subcontractor: str
    total: int
    open_defects: int
    overdue_defects: int
    health_score: Decimal | None = None

    @field_serializer("health_score", when_used="json")
    def _ser_health(self, v: Decimal | None) -> str | None:
        return _serialise_pct(v)


class DlpRegisterResponse(BaseModel):
    """The full defects-liability register rollup for a project."""

    project_id: UUID
    as_of: str
    horizon_days: int
    total: int
    per_status: dict[str, int] = Field(default_factory=dict)
    per_warranty_type: dict[str, int] = Field(default_factory=dict)
    total_open_defects: int
    overall_health_score: Decimal | None = None
    is_clean: bool
    expiring: list[WarrantyRef] = Field(default_factory=list)
    expired: list[WarrantyRef] = Field(default_factory=list)
    overdue_defects: list[OverdueDefectRef] = Field(default_factory=list)
    retention_release_ready: list[WarrantyRef] = Field(default_factory=list)
    subcontractors: list[SubcontractorDlpHealthResponse] = Field(default_factory=list)

    @field_serializer("overall_health_score", when_used="json")
    def _ser_pct(self, v: Decimal | None) -> str | None:
        return _serialise_pct(v)


class RetentionReleaseReadinessResponse(BaseModel):
    """The entries clear for final retention release as of a date.

    Answers the single question the post-handover team asks when planning
    retention payments: which entries have run out their defects liability period
    with nothing left outstanding, so the money held back can be released.
    """

    project_id: UUID
    as_of: str
    total: int
    ready_count: int
    ready: list[WarrantyRef] = Field(default_factory=list)
