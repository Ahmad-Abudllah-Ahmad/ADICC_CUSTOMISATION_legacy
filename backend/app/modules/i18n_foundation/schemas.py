# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Internationalization foundation Pydantic schemas for request/response validation.

Covers exchange rates, countries, work calendars, tax configurations,
and utility schemas for currency conversion and working-day calculations.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── ExchangeRate ─────────────────────────────────────────────────────────


class ExchangeRateCreate(BaseModel):
    """Create a new exchange rate entry."""

    from_currency: str = Field(..., min_length=3, max_length=3)
    to_currency: str = Field(..., min_length=3, max_length=3)
    rate: str = Field(..., min_length=1, max_length=50)
    rate_date: str = Field(..., min_length=1, max_length=20)
    source: str = Field(default="manual", max_length=50)
    is_manual: bool = Field(default=True)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExchangeRateUpdate(BaseModel):
    """Update an exchange rate (all fields optional)."""

    from_currency: str | None = Field(default=None, min_length=3, max_length=3)
    to_currency: str | None = Field(default=None, min_length=3, max_length=3)
    rate: str | None = Field(default=None, min_length=1, max_length=50)
    rate_date: str | None = Field(default=None, min_length=1, max_length=20)
    source: str | None = Field(default=None, max_length=50)
    is_manual: bool | None = None
    metadata: dict[str, Any] | None = None


class ExchangeRateResponse(BaseModel):
    """Exchange rate in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    from_currency: str
    to_currency: str
    rate: str
    rate_date: str
    source: str
    is_manual: bool
    metadata: dict[str, Any] = Field(alias="metadata_")
    created_at: datetime
    updated_at: datetime


class ExchangeRateListResponse(BaseModel):
    """Paginated list of exchange rates."""

    items: list[ExchangeRateResponse]
    total: int


# ── Country ──────────────────────────────────────────────────────────────


class CountryResponse(BaseModel):
    """Country in API responses.

    Countries are seeded - no Create/Update schemas needed for now.
    Admin endpoints will be added later.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    iso_code: str
    iso_code_3: str | None
    name_en: str
    name_translations: dict[str, str]
    currency_default: str | None
    measurement_default: str | None
    phone_code: str | None
    address_format_template: dict[str, Any] | None
    region_group: str | None
    is_active: bool
    metadata: dict[str, Any] = Field(alias="metadata_")
    created_at: datetime


class CountryListResponse(BaseModel):
    """Paginated list of countries."""

    items: list[CountryResponse]
    total: int


# ── WorkCalendar ─────────────────────────────────────────────────────────


class WorkCalendarCreate(BaseModel):
    """Create a new work calendar."""

    country_code: str = Field(..., min_length=2, max_length=2)
    name: str = Field(..., min_length=1, max_length=255)
    name_translations: dict[str, str] | None = None
    year: str = Field(..., min_length=4, max_length=4)
    work_hours_per_day: str = Field(default="8", max_length=10)
    work_days: list[int] = Field(..., min_length=1)
    exceptions: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkCalendarUpdate(BaseModel):
    """Update a work calendar (all fields optional)."""

    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    name_translations: dict[str, str] | None = None
    year: str | None = Field(default=None, min_length=4, max_length=4)
    work_hours_per_day: str | None = Field(default=None, max_length=10)
    work_days: list[int] | None = None
    exceptions: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None


class WorkCalendarResponse(BaseModel):
    """Work calendar in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    country_code: str
    name: str
    name_translations: dict[str, str] | None
    year: str
    work_hours_per_day: str
    work_days: list[int]
    exceptions: list[dict[str, Any]]
    metadata: dict[str, Any] = Field(alias="metadata_")
    created_at: datetime
    updated_at: datetime


class WorkCalendarListResponse(BaseModel):
    """Paginated list of work calendars."""

    items: list[WorkCalendarResponse]
    total: int


# ── TaxConfiguration ─────────────────────────────────────────────────────


class TaxConfigCreate(BaseModel):
    """Create a new tax configuration."""

    country_code: str = Field(..., min_length=2, max_length=2)
    tax_name: str = Field(..., min_length=1, max_length=255)
    tax_name_translations: dict[str, str] | None = None
    tax_code: str | None = Field(default=None, max_length=50)
    rate_pct: str = Field(..., min_length=1, max_length=20)
    tax_type: str = Field(..., min_length=1, max_length=50)
    effective_from: str | None = Field(default=None, max_length=20)
    effective_to: str | None = Field(default=None, max_length=20)
    is_default: bool = Field(default=False)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaxConfigUpdate(BaseModel):
    """Update a tax configuration (all fields optional)."""

    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    tax_name: str | None = Field(default=None, min_length=1, max_length=255)
    tax_name_translations: dict[str, str] | None = None
    tax_code: str | None = Field(default=None, max_length=50)
    rate_pct: str | None = Field(default=None, min_length=1, max_length=20)
    tax_type: str | None = Field(default=None, min_length=1, max_length=50)
    effective_from: str | None = Field(default=None, max_length=20)
    effective_to: str | None = Field(default=None, max_length=20)
    is_default: bool | None = None
    metadata: dict[str, Any] | None = None


class TaxConfigResponse(BaseModel):
    """Tax configuration in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    country_code: str
    tax_name: str
    tax_name_translations: dict[str, str] | None
    tax_code: str | None
    rate_pct: str
    tax_type: str
    effective_from: str | None
    effective_to: str | None
    is_default: bool
    metadata: dict[str, Any] = Field(alias="metadata_")
    created_at: datetime
    updated_at: datetime


class TaxConfigListResponse(BaseModel):
    """Paginated list of tax configurations."""

    items: list[TaxConfigResponse]
    total: int


# ── Utility Schemas ──────────────────────────────────────────────────────


class ConvertRequest(BaseModel):
    """Request to convert an amount between currencies."""

    from_currency: str = Field(..., min_length=3, max_length=3)
    to_currency: str = Field(..., min_length=3, max_length=3)
    amount: str = Field(..., min_length=1)
    date: str | None = Field(default=None, max_length=20)


class ConvertResponse(BaseModel):
    """Result of a currency conversion."""

    original_amount: str
    converted_amount: str
    from_currency: str
    to_currency: str
    rate: str
    rate_date: str


class WorkingDaysRequest(BaseModel):
    """Request to calculate working days between two dates."""

    country_code: str = Field(..., min_length=2, max_length=2)
    from_date: str = Field(..., min_length=1, max_length=20)
    to_date: str = Field(..., min_length=1, max_length=20)


class WorkingDaysResponse(BaseModel):
    """Result of a working-days calculation."""

    country_code: str
    from_date: str
    to_date: str
    working_days: int
    calendar_days: int
