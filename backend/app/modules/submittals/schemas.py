# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Submittals Pydantic schemas - request/response models."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SubmittalCreate(BaseModel):
    """Create a new submittal."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    spec_section: str | None = Field(default=None, max_length=100)
    submittal_type: str = Field(
        ...,
        pattern=(
            r"^(shop_drawing|product_data|sample|mock_up|"
            r"test_report|certificate|warranty)$"
        ),
    )
    status: str = Field(
        default="draft",
        pattern=(
            r"^(draft|submitted|under_review|approved|"
            r"approved_as_noted|revise_and_resubmit|rejected|closed)$"
        ),
    )
    ball_in_court: str | None = Field(default=None, max_length=100)
    current_revision: int = Field(default=1, ge=1)
    submitted_by_org: str | None = Field(default=None, max_length=255)
    reviewer_id: str | None = Field(default=None, max_length=36)
    approver_id: str | None = Field(default=None, max_length=36)
    date_submitted: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_required: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_returned: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    linked_boq_item_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SubmittalUpdate(BaseModel):
    """Partial update for a submittal."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    spec_section: str | None = Field(default=None, max_length=100)
    submittal_type: str | None = Field(
        default=None,
        pattern=(
            r"^(shop_drawing|product_data|sample|mock_up|"
            r"test_report|certificate|warranty)$"
        ),
    )
    status: str | None = Field(
        default=None,
        pattern=(
            r"^(draft|submitted|under_review|approved|"
            r"approved_as_noted|revise_and_resubmit|rejected|closed)$"
        ),
    )
    ball_in_court: str | None = Field(default=None, max_length=100)
    current_revision: int | None = Field(default=None, ge=1)
    submitted_by_org: str | None = Field(default=None, max_length=255)
    reviewer_id: str | None = Field(default=None, max_length=36)
    approver_id: str | None = Field(default=None, max_length=36)
    date_submitted: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_required: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_returned: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    linked_boq_item_ids: list[str] | None = None
    metadata: dict[str, Any] | None = None


class SubmittalReviewRequest(BaseModel):
    """Request body for reviewing a submittal."""

    status: str = Field(
        ...,
        pattern=(r"^(approved|approved_as_noted|revise_and_resubmit|rejected)$"),
    )
    notes: str | None = Field(default=None, max_length=5000)


class SubmittalApproveRequest(BaseModel):
    """Optional request body for final approval.

    The body is optional (a bare ``POST /approve/`` still works), but when
    present it carries the approver's ``notes`` so an approval with comments
    persists them into the submittal metadata instead of dropping them.
    """

    notes: str | None = Field(default=None, max_length=5000)


class StartApprovalRequest(BaseModel):
    """Request body for starting a routed approval workflow (feature 06)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    route_id: UUID


class SubmittalResponse(BaseModel):
    """Submittal returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    submittal_number: str
    title: str
    spec_section: str | None = None
    submittal_type: str
    status: str = "draft"
    ball_in_court: str | None = None
    ball_in_court_name: str | None = None
    current_revision: int = 1
    submitted_by_org: str | None = None
    reviewer_id: str | None = None
    approver_id: str | None = None
    date_submitted: str | None = None
    date_required: str | None = None
    date_returned: str | None = None
    linked_boq_item_ids: list[str] = Field(default_factory=list)
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    # Description and reviewer notes are persisted inside ``metadata`` (the
    # Submittal model has no dedicated columns and we add no migration). They
    # are surfaced as top-level convenience fields by ``_to_response`` so the
    # frontend does not have to dig into the metadata blob.
    description: str | None = None
    review_notes: str | None = None
    created_at: datetime
    updated_at: datetime
