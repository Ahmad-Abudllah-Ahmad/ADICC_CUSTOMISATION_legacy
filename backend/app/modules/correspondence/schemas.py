# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Correspondence Pydantic schemas - request/response models."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _sanitize_email_header_value(value: str) -> str:
    """Strip CR/LF and other control chars from a string destined for an
    email header (Subject) or HTML-rendered field.

    Email-header injection: an attacker who can insert ``\\r\\n`` into a
    subject can append arbitrary headers ("Bcc: ...", "Content-Type: ...")
    or even break the header / body boundary and inject a forged body. We
    forbid every C0 control character except TAB so the model layer can't
    produce an unsafe outgoing message regardless of what the SMTP sender
    does. The same scrubbing makes the value safe for raw textContent
    rendering on the frontend (no HTML tag here means no XSS via subject).
    """
    if not value:
        return value
    # Remove CR, LF, NUL and the rest of the C0 range except TAB (\x09).
    cleaned = "".join(ch for ch in value if ch == "\t" or ord(ch) >= 0x20)
    # Collapse any internal whitespace runs left by the strip - email
    # subjects with embedded ``\r\n`` would otherwise become double-space.
    return " ".join(cleaned.split())


class CorrespondenceCreate(BaseModel):
    """Create a new correspondence record."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    direction: str = Field(..., pattern=r"^(incoming|outgoing)$")
    subject: str = Field(..., min_length=1, max_length=500)
    from_contact_id: str | None = None
    to_contact_ids: list[str] = Field(default_factory=list)
    date_sent: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_received: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    correspondence_type: str = Field(
        ...,
        pattern=r"^(letter|email|notice|memo)$",
    )
    linked_document_ids: list[str] = Field(default_factory=list)
    linked_transmittal_id: str | None = None
    linked_rfi_id: str | None = None
    status: str = Field(
        default="open",
        pattern=r"^(open|awaiting_response|responded|closed)$",
    )
    response_required_by: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    contract_clause_ref: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("subject")
    @classmethod
    def _subject_no_header_injection(cls, value: str) -> str:
        cleaned = _sanitize_email_header_value(value)
        if not cleaned:
            raise ValueError("subject is empty after sanitisation")
        return cleaned

    @field_validator("contract_clause_ref")
    @classmethod
    def _clause_no_control_chars(cls, value: str | None) -> str | None:
        # The clause pointer is rendered as raw text on the frontend and can
        # end up in an exported cover sheet, so scrub control characters the
        # same way the subject is scrubbed. An all-whitespace value collapses
        # to None rather than a stored blank.
        if value is None:
            return None
        cleaned = _sanitize_email_header_value(value)
        return cleaned or None


class CorrespondenceUpdate(BaseModel):
    """Partial update for a correspondence record."""

    model_config = ConfigDict(str_strip_whitespace=True)

    direction: str | None = Field(default=None, pattern=r"^(incoming|outgoing)$")
    subject: str | None = Field(default=None, min_length=1, max_length=500)
    from_contact_id: str | None = None
    to_contact_ids: list[str] | None = None
    date_sent: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_received: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    correspondence_type: str | None = Field(
        default=None,
        pattern=r"^(letter|email|notice|memo)$",
    )
    linked_document_ids: list[str] | None = None
    linked_transmittal_id: str | None = None
    linked_rfi_id: str | None = None
    status: str | None = Field(
        default=None,
        pattern=r"^(open|awaiting_response|responded|closed)$",
    )
    response_required_by: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    contract_clause_ref: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=5000)
    metadata: dict[str, Any] | None = None

    @field_validator("subject")
    @classmethod
    def _subject_no_header_injection(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = _sanitize_email_header_value(value)
        if not cleaned:
            raise ValueError("subject is empty after sanitisation")
        return cleaned

    @field_validator("contract_clause_ref")
    @classmethod
    def _clause_no_control_chars(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = _sanitize_email_header_value(value)
        return cleaned or None


class CorrespondenceResponse(BaseModel):
    """Correspondence returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    reference_number: str
    direction: str
    subject: str
    from_contact_id: str | None = None
    to_contact_ids: list[str] = Field(default_factory=list)
    date_sent: str | None = None
    date_received: str | None = None
    correspondence_type: str
    linked_document_ids: list[str] = Field(default_factory=list)
    linked_transmittal_id: str | None = None
    linked_rfi_id: str | None = None
    status: str = "open"
    response_required_by: str | None = None
    contract_clause_ref: str | None = None
    # Computed at serialisation time from ``response_required_by`` + ``status``;
    # never stored. ``is_overdue`` is True when a still-open record has passed
    # its deadline; ``days_until_due`` is signed (negative once overdue).
    is_overdue: bool = False
    days_until_due: int | None = None
    notes: str | None = None
    created_by: str | None = None
    attachments: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime
