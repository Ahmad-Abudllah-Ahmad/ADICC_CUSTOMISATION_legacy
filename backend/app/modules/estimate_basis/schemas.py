# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Estimate-basis request / response schemas.

Money rollups on the coverage summary arrive as Decimal-as-string, matching the
rest of the estimating surface; nothing here routes a total through a float.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

QualificationCategory = Literal["inclusion", "exclusion", "assumption"]


class QualificationItem(BaseModel):
    """One editable line of the basis-of-estimate."""

    id: str = Field(..., description="Stable id, unique within the document.")
    category: QualificationCategory
    text: str = Field(..., max_length=2000)
    trade_code: str | None = None
    trade_label: str | None = None
    basis: str = Field(default="", description="Why the line was drafted: present/absent/flag/standard.")
    source: Literal["auto", "manual"] = "auto"
    enabled: bool = True


class TradePresenceOut(BaseModel):
    """A trade present in the estimate, with its rollup."""

    code: str
    label: str
    core: bool
    position_count: int
    total: str = Field(..., description="Rolled-up total for the trade (Decimal string).")


class TradeRefOut(BaseModel):
    """A reference to a trade (used for absent/expected trades)."""

    code: str
    label: str


class CoverageSummary(BaseModel):
    """The present / absent / flagged picture the basis was drafted from."""

    present_trades: list[TradePresenceOut] = Field(default_factory=list)
    absent_trades: list[TradeRefOut] = Field(default_factory=list)
    total_positions: int = 0
    classified_positions: int = 0
    unclassified_positions: int = 0
    zero_rate_positions: int = 0
    missing_quantity_positions: int = 0
    provisional_positions: int = 0
    by_others_positions: int = 0


class GenerateRequest(BaseModel):
    """Draft a fresh basis-of-estimate from a project's estimate contents."""

    project_id: uuid.UUID
    boq_id: uuid.UUID | None = Field(
        default=None,
        description="Restrict the derivation to one BOQ; omit to span the whole project.",
    )
    title: str | None = Field(default=None, max_length=255)
    currency: str = Field(default="", max_length=8)
    base_date: str | None = Field(default=None, max_length=40)


class UpdateRequest(BaseModel):
    """Persist user edits to a drafted basis-of-estimate.

    Every field is optional so the client can patch a single list (e.g. only the
    exclusions) without echoing the whole document back.
    """

    title: str | None = Field(default=None, max_length=255)
    status: Literal["draft", "final"] | None = None
    notes: str | None = Field(default=None, max_length=8000)
    inclusions: list[QualificationItem] | None = None
    exclusions: list[QualificationItem] | None = None
    assumptions: list[QualificationItem] | None = None


class EstimateBasisResponse(BaseModel):
    """A full basis-of-estimate document."""

    id: str
    project_id: str
    boq_id: str | None
    title: str
    status: str
    notes: str
    inclusions: list[QualificationItem]
    exclusions: list[QualificationItem]
    assumptions: list[QualificationItem]
    coverage: CoverageSummary
    generated_at: str | None
    created_at: str | None
    updated_at: str | None


class EstimateBasisSummary(BaseModel):
    """A lightweight row for the per-project document list."""

    id: str
    project_id: str
    boq_id: str | None
    title: str
    status: str
    inclusion_count: int
    exclusion_count: int
    assumption_count: int
    generated_at: str | None
    created_at: str | None
    updated_at: str | None


class EstimateBasisListResponse(BaseModel):
    """The documents drafted for one project, newest first."""

    project_id: str
    items: list[EstimateBasisSummary] = Field(default_factory=list)
