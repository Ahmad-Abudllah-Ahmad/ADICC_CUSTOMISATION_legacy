# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Contracts Pydantic schemas - request / response models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Contract ─────────────────────────────────────────────────────────────

CONTRACT_TYPES = "lump_sum|gmp|cost_plus|tm|unit_price|design_build|combination|remeasurement"
COUNTERPARTY_TYPES = "client|subcontractor"
CONTRACT_STATUSES = "draft|active|suspended|completed|terminated"
RETENTION_RELEASE_EVENTS = "practical_completion|final_account|handover"


class ContractCreate(BaseModel):
    """Create a new contract."""

    model_config = ConfigDict(str_strip_whitespace=True)

    code: str = Field(..., min_length=1, max_length=80)
    title: str = Field(default="", max_length=500)
    contract_type: str = Field(..., pattern=rf"^({CONTRACT_TYPES})$")
    counterparty_type: str = Field(default="client", pattern=rf"^({COUNTERPARTY_TYPES})$")
    counterparty_id: UUID | None = None
    project_id: UUID
    parent_contract_id: UUID | None = None
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    total_value: Decimal = Field(default=Decimal("0"))
    currency: str = Field(default="", max_length=3)
    retention_percent: Decimal = Field(default=Decimal("5.00"), ge=0, le=100)
    retention_release_event: str = Field(
        default="practical_completion",
        pattern=rf"^({RETENTION_RELEASE_EVENTS})$",
    )
    status: str = Field(default="draft", pattern=rf"^({CONTRACT_STATUSES})$")
    signed_at: str | None = None
    terms: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContractUpdate(BaseModel):
    """Partial update for a contract."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, max_length=500)
    contract_type: str | None = Field(default=None, pattern=rf"^({CONTRACT_TYPES})$")
    counterparty_type: str | None = Field(default=None, pattern=rf"^({COUNTERPARTY_TYPES})$")
    counterparty_id: UUID | None = None
    parent_contract_id: UUID | None = None
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    total_value: Decimal | None = None
    currency: str | None = Field(default=None, max_length=3)
    retention_percent: Decimal | None = Field(default=None, ge=0, le=100)
    retention_release_event: str | None = Field(
        default=None,
        pattern=rf"^({RETENTION_RELEASE_EVENTS})$",
    )
    status: str | None = Field(default=None, pattern=rf"^({CONTRACT_STATUSES})$")
    signed_at: str | None = None
    terms: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class ContractResponse(BaseModel):
    """A contract as returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    code: str
    title: str
    contract_type: str
    counterparty_type: str
    counterparty_id: UUID | None = None
    project_id: UUID
    parent_contract_id: UUID | None = None
    start_date: str | None = None
    end_date: str | None = None
    total_value: Decimal
    currency: str
    retention_percent: Decimal
    retention_release_event: str
    status: str
    signed_at: str | None = None
    terms: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── ContractLine (SoV) ───────────────────────────────────────────────────


LINE_TYPES = "work|material|labor|fee|contingency|allowance"


class ContractLineCreate(BaseModel):
    """Create a new SoV line."""

    model_config = ConfigDict(str_strip_whitespace=True)

    contract_id: UUID
    parent_line_id: UUID | None = None
    code: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=2000)
    scope_section: str | None = Field(default=None, max_length=255)
    line_type: str = Field(default="work", pattern=rf"^({LINE_TYPES})$")
    unit: str | None = Field(default=None, max_length=20)
    quantity: Decimal = Field(default=Decimal("0"))
    unit_rate: Decimal = Field(default=Decimal("0"))
    order_index: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContractLineUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    parent_line_id: UUID | None = None
    code: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    scope_section: str | None = Field(default=None, max_length=255)
    line_type: str | None = Field(default=None, pattern=rf"^({LINE_TYPES})$")
    unit: str | None = Field(default=None, max_length=20)
    quantity: Decimal | None = None
    unit_rate: Decimal | None = None
    order_index: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] | None = None


class ContractLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    contract_id: UUID
    parent_line_id: UUID | None = None
    code: str
    description: str
    scope_section: str | None = None
    line_type: str
    unit: str | None = None
    quantity: Decimal
    unit_rate: Decimal
    total_value: Decimal
    order_index: int
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class ContractLineBulkCreate(BaseModel):
    """Bulk-insert SoV lines for a contract."""

    lines: list[ContractLineCreate] = Field(default_factory=list)


class ContractCloneRequest(BaseModel):
    """Clone an existing contract into the same or a different project.

    The clone is always created in ``draft`` status: a copy of a live
    contract must be re-signed before becoming commercially binding,
    otherwise the cloned signed_at would falsely represent a wet
    signature on the new instrument.

    Body fields:
        target_project_id: destination project - defaults to the source
            contract's project. When supplied, the caller must have
            project-level access on the DESTINATION (else 404), in
            addition to read access on the SOURCE (also 404).
        new_code: contract code for the clone - required and must be
            unique (``oe_contracts_contract.code`` is a UNIQUE column).
        new_title: human title; defaults to ``"<source.title> (clone)"``.
        include_lines: copy all Schedule-of-Values lines (default True).
        copy_subconfigs: copy retention schedule / fee structure /
            gainshare config / LD clauses (default True). Progress
            claims, final accounts, lien waivers and retention-release
            audit entries are NEVER cloned - those belong to the
            original contract's payment history.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    target_project_id: UUID | None = None
    new_code: str = Field(..., min_length=1, max_length=80)
    new_title: str | None = Field(default=None, max_length=500)
    include_lines: bool = True
    copy_subconfigs: bool = True


# ── ContractTypeConfiguration ────────────────────────────────────────────


class ContractTypeConfigurationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contract_type: str
    display_name: str
    allowed_fields: list[str] = Field(default_factory=list)
    default_fee_structure: dict[str, Any] = Field(default_factory=dict)
    schema_version: str


# ── RetentionSchedule ────────────────────────────────────────────────────


class RetentionScheduleCreate(BaseModel):
    contract_id: UUID
    accrual_rule: dict[str, Any] = Field(default_factory=dict)
    release_rule: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class RetentionScheduleUpdate(BaseModel):
    accrual_rule: dict[str, Any] | None = None
    release_rule: dict[str, Any] | None = None
    notes: str | None = None


class RetentionScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contract_id: UUID
    accrual_rule: dict[str, Any] = Field(default_factory=dict)
    release_rule: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


# ── FeeStructure ─────────────────────────────────────────────────────────


FEE_TYPES = "percent_of_cost|fixed|sliding_scale"


class FeeStructureCreate(BaseModel):
    contract_id: UUID
    fee_type: str = Field(default="percent_of_cost", pattern=rf"^({FEE_TYPES})$")
    fee_percent: Decimal = Field(default=Decimal("0"), ge=0)
    fee_fixed_amount: Decimal | None = None
    sliding_scale: list[dict[str, Any]] = Field(default_factory=list)
    max_fee: Decimal | None = None


class FeeStructureUpdate(BaseModel):
    fee_type: str | None = Field(default=None, pattern=rf"^({FEE_TYPES})$")
    fee_percent: Decimal | None = Field(default=None, ge=0)
    fee_fixed_amount: Decimal | None = None
    sliding_scale: list[dict[str, Any]] | None = None
    max_fee: Decimal | None = None


class FeeStructureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contract_id: UUID
    fee_type: str
    fee_percent: Decimal
    fee_fixed_amount: Decimal | None = None
    sliding_scale: list[dict[str, Any]] = Field(default_factory=list)
    max_fee: Decimal | None = None
    created_at: datetime
    updated_at: datetime


# ── GainshareConfiguration ───────────────────────────────────────────────


OVERRUN_RESPONSIBILITIES = "contractor|shared|owner"


class GainshareConfigurationCreate(BaseModel):
    contract_id: UUID
    target_cost: Decimal = Field(default=Decimal("0"))
    gmp_cap: Decimal = Field(default=Decimal("0"))
    savings_split_owner_pct: Decimal = Field(default=Decimal("50"), ge=0, le=100)
    savings_split_contractor_pct: Decimal = Field(default=Decimal("50"), ge=0, le=100)
    overrun_responsibility: str = Field(
        default="contractor",
        pattern=rf"^({OVERRUN_RESPONSIBILITIES})$",
    )


class GainshareConfigurationUpdate(BaseModel):
    target_cost: Decimal | None = None
    gmp_cap: Decimal | None = None
    savings_split_owner_pct: Decimal | None = Field(default=None, ge=0, le=100)
    savings_split_contractor_pct: Decimal | None = Field(default=None, ge=0, le=100)
    overrun_responsibility: str | None = Field(
        default=None,
        pattern=rf"^({OVERRUN_RESPONSIBILITIES})$",
    )


class GainshareConfigurationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contract_id: UUID
    target_cost: Decimal
    gmp_cap: Decimal
    savings_split_owner_pct: Decimal
    savings_split_contractor_pct: Decimal
    overrun_responsibility: str
    created_at: datetime
    updated_at: datetime


# ── LDClause ─────────────────────────────────────────────────────────────


LD_ENFORCEMENT_STATUSES = "active|waived"


class LDClauseCreate(BaseModel):
    contract_id: UUID
    per_day_amount: Decimal = Field(default=Decimal("0"))
    currency: str = Field(default="", max_length=3)
    max_amount: Decimal | None = None
    milestone_id: UUID | None = None
    enforcement_status: str = Field(
        default="active",
        pattern=rf"^({LD_ENFORCEMENT_STATUSES})$",
    )


class LDClauseUpdate(BaseModel):
    per_day_amount: Decimal | None = None
    currency: str | None = Field(default=None, max_length=3)
    max_amount: Decimal | None = None
    milestone_id: UUID | None = None
    enforcement_status: str | None = Field(
        default=None,
        pattern=rf"^({LD_ENFORCEMENT_STATUSES})$",
    )


class LDClauseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contract_id: UUID
    per_day_amount: Decimal
    currency: str
    max_amount: Decimal | None = None
    milestone_id: UUID | None = None
    enforcement_status: str
    created_at: datetime
    updated_at: datetime


# ── ProgressClaim ────────────────────────────────────────────────────────


CLAIM_STATUSES = "draft|submitted|approved|certified|paid|rejected"


class ProgressClaimCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    contract_id: UUID
    claim_number: str | None = Field(default=None, max_length=40)
    period_start: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    period_end: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    claim_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    currency: str = Field(default="", max_length=3)
    milestone_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProgressClaimUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    claim_number: str | None = Field(default=None, max_length=40)
    period_start: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    period_end: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    claim_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    status: str | None = Field(default=None, pattern=rf"^({CLAIM_STATUSES})$")
    currency: str | None = Field(default=None, max_length=3)
    milestone_id: UUID | None = None
    metadata: dict[str, Any] | None = None


class ProgressClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    contract_id: UUID
    claim_number: str
    period_start: str | None = None
    period_end: str | None = None
    claim_date: str | None = None
    gross_amount: Decimal
    retention_amount: Decimal
    prior_claims_total: Decimal
    net_due: Decimal
    status: str
    submitted_at: str | None = None
    approved_at: str | None = None
    paid_at: str | None = None
    currency: str
    milestone_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class ProgressClaimLineCreate(BaseModel):
    progress_claim_id: UUID
    contract_line_id: UUID
    period_completed_qty: Decimal = Field(default=Decimal("0"))
    period_completed_value: Decimal = Field(default=Decimal("0"))
    period_completed_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    cumulative_completed_value: Decimal = Field(default=Decimal("0"))


class ProgressClaimLineUpdate(BaseModel):
    period_completed_qty: Decimal | None = None
    period_completed_value: Decimal | None = None
    period_completed_pct: Decimal | None = Field(default=None, ge=0, le=100)
    cumulative_completed_value: Decimal | None = None


class ProgressClaimLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    progress_claim_id: UUID
    contract_line_id: UUID
    period_completed_qty: Decimal
    period_completed_value: Decimal
    period_completed_pct: Decimal
    cumulative_completed_value: Decimal
    created_at: datetime
    updated_at: datetime


class AutoGenerateClaimRequest(BaseModel):
    """Payload to auto-generate a ProgressClaim from completion data."""

    completion: dict[str, Decimal] = Field(
        default_factory=dict,
        description="contract_line_id (str) → completion percent (0-100)",
    )
    measurements: dict[str, Decimal] = Field(
        default_factory=dict,
        description="contract_line_id (str) → period-completed quantity (unit-price)",
    )
    actual_costs_total: Decimal | None = Field(
        default=None,
        description="Total actual costs incurred this period (cost-plus / T&M)",
    )
    time_entries_total: Decimal | None = Field(
        default=None,
        description="T&M: total labor / equipment hours value this period",
    )
    material_entries_total: Decimal | None = Field(
        default=None,
        description="T&M: total materials value this period",
    )


# ── Progress-claim bridge (Gap I) ────────────────────────────────────────


class ProgressClaimPopulatePreviewItem(BaseModel):
    """One previewed claim line derived from a progress observation.

    The preview is read-only: it shows what the claim line WOULD become if the
    user commits, so the UI can let the user deselect / tweak before saving.
    All monetary values are Decimal-as-string in the claim's currency.
    """

    contract_line_id: UUID
    contract_line_code: str = ""
    contract_line_description: str = ""
    boq_position_id: UUID
    unit: str | None = None
    contract_quantity: Decimal = Field(default=Decimal("0"))
    contract_line_value: Decimal = Field(default=Decimal("0"))
    # Latest observed percent-complete for the linked BOQ position (0-100).
    observed_pct: Decimal = Field(default=Decimal("0"))
    period_label: str | None = None
    recorded_at: datetime | None = None
    # Derived figures at the observed percent.
    period_completed_qty: Decimal = Field(default=Decimal("0"))
    period_completed_value: Decimal = Field(default=Decimal("0"))
    cumulative_completed_value: Decimal = Field(default=Decimal("0"))


class ProgressClaimPopulatePreviewResponse(BaseModel):
    """Preview payload for ``GET /populate-from-progress``.

    ``items`` are the populatable lines (SoV lines that link to a BOQ position
    which has at least one progress observation). ``skipped_unlinked`` counts
    SoV lines with no BOQ-position link, ``skipped_no_progress`` counts linked
    lines that have no observation yet - both surfaced so the UI can hint why a
    line is absent. ``currency`` is the claim currency the values are expressed
    in (never a blend).
    """

    claim_id: UUID
    contract_id: UUID
    currency: str = ""
    items: list[ProgressClaimPopulatePreviewItem] = Field(default_factory=list)
    skipped_unlinked: int = 0
    skipped_no_progress: int = 0
    skipped_foreign_currency: int = 0
    gross: Decimal = Field(default=Decimal("0"))
    retention: Decimal = Field(default=Decimal("0"))
    prior_claims_total: Decimal = Field(default=Decimal("0"))
    net_due: Decimal = Field(default=Decimal("0"))


class ProgressClaimCommitLine(BaseModel):
    """One line the client commits back after editing the preview.

    The client echoes the contract_line_id and the (possibly user-adjusted)
    value/percent it wants persisted. Quantities/values are recomputed and
    re-rolled-up server-side, so a tampered total cannot inflate the claim
    beyond the contract line value.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    contract_line_id: UUID
    period_completed_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    # Optional explicit value override; when omitted the value is derived from
    # the percent × contract line value. When supplied it is clamped to the
    # contract line value so the claim line can never exceed the SoV line.
    period_completed_value: Decimal | None = None


class ProgressClaimCommitRequest(BaseModel):
    """Body for ``PUT /commit-populated-lines``."""

    lines: list[ProgressClaimCommitLine] = Field(default_factory=list)


# ── FinalAccount ─────────────────────────────────────────────────────────


FINAL_ACCOUNT_STATUSES = "draft|agreed|disputed|closed"


class FinalAccountCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    contract_id: UUID
    final_contract_value: Decimal = Field(default=Decimal("0"))
    total_paid: Decimal = Field(default=Decimal("0"))
    retention_held: Decimal = Field(default=Decimal("0"))
    retention_released: Decimal = Field(default=Decimal("0"))
    final_balance: Decimal = Field(default=Decimal("0"))
    sign_off_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    sign_off_by: str | None = None
    status: str = Field(default="draft", pattern=rf"^({FINAL_ACCOUNT_STATUSES})$")
    notes: str | None = None


class FinalAccountUpdate(BaseModel):
    final_contract_value: Decimal | None = None
    total_paid: Decimal | None = None
    retention_held: Decimal | None = None
    retention_released: Decimal | None = None
    final_balance: Decimal | None = None
    sign_off_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    sign_off_by: str | None = None
    status: str | None = Field(default=None, pattern=rf"^({FINAL_ACCOUNT_STATUSES})$")
    notes: str | None = None


class FinalAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contract_id: UUID
    final_contract_value: Decimal
    total_paid: Decimal
    retention_held: Decimal
    retention_released: Decimal
    final_balance: Decimal
    sign_off_date: str | None = None
    sign_off_by: str | None = None
    status: str
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


# ── Calculated summaries ─────────────────────────────────────────────────


class ContractTotalsResponse(BaseModel):
    """Calculated totals & SoV rollup for a Contract."""

    contract_id: UUID
    total_value: Decimal
    line_total: Decimal
    paid_to_date: Decimal
    retention_held: Decimal
    outstanding: Decimal
    line_count: int


class ProgressClaimSummary(BaseModel):
    """Computed totals for a ProgressClaim."""

    gross: Decimal
    retention: Decimal
    prior_claims_paid: Decimal
    net: Decimal


class GainshareCalculation(BaseModel):
    """Result of a GMP gainshare / overrun computation."""

    actual_cost: Decimal
    target_cost: Decimal
    gmp_cap: Decimal
    savings: Decimal
    owner_share: Decimal
    contractor_share: Decimal
    overrun: Decimal
    overrun_responsibility: str


class FinalAccountSummary(BaseModel):
    """Computed balances on a closed contract."""

    contract_id: UUID
    final_contract_value: Decimal
    total_paid: Decimal
    retention_held: Decimal
    retention_released: Decimal
    final_balance: Decimal
    status: str


class ContractDashboardResponse(BaseModel):
    """Dashboard summary for a single contract."""

    contract_id: UUID
    total_value: Decimal
    paid_to_date: Decimal
    retention_held: Decimal
    outstanding: Decimal
    claims_count: int
    change_orders_count: int
    gainshare_estimate: Decimal | None = None
    status: str


# ── AIA G702/G703 (US/CA/AU only) ──────────────────────────────────────────


class AIAG703Line(BaseModel):
    """One G703 continuation-sheet row."""

    line_number: int
    item_number: str
    description: str
    scheduled_value: Decimal
    previous_value: Decimal
    this_period_value: Decimal
    materials_stored: Decimal
    total_completed_stored: Decimal
    percent_complete: Decimal
    balance_to_finish: Decimal
    retainage: Decimal


class AIAG702Summary(BaseModel):
    """G702 certificate-face summary."""

    original_contract_sum: Decimal
    change_orders_net: Decimal
    contract_sum_to_date: Decimal
    total_completed_stored: Decimal
    retainage: Decimal
    total_earned_less_retainage: Decimal
    previous_certificates_total: Decimal
    current_payment_due: Decimal
    balance_to_finish: Decimal


class AIACertification(BaseModel):
    """Architect / owner certification block stamped on the application."""

    architect_certified_at: str | None = None
    architect_certified_by: str | None = None
    owner_certified_at: str | None = None
    owner_certified_by: str | None = None
    certified_amount: Decimal | None = None


class AIAApplicationResponse(BaseModel):
    """Full AIA G702 + G703 payment-application view for one progress claim."""

    claim_id: UUID
    contract_id: UUID
    project_id: UUID
    application_number: str
    period_start: str | None = None
    period_end: str | None = None
    claim_date: str | None = None
    currency: str
    claim_status: str
    retainage_percent: Decimal
    summary: AIAG702Summary
    lines: list[AIAG703Line]
    certification: AIACertification


# == ContractParty (structured parties / roles) ============================


PARTY_ROLES = "employer|contractor|subcontractor|consultant|architect|engineer|guarantor|other"
PARTY_TYPES = "contact|subcontractor|user|external"


class ContractPartyCreate(BaseModel):
    """Create a structured party / role on a contract."""

    model_config = ConfigDict(str_strip_whitespace=True)

    contract_id: UUID
    party_role: str = Field(default="other", pattern=rf"^({PARTY_ROLES})$")
    party_type: str = Field(default="external", pattern=rf"^({PARTY_TYPES})$")
    party_id: UUID | None = None
    display_name: str = Field(default="", max_length=500)
    is_primary: bool = False
    contact_details: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContractPartyUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    party_role: str | None = Field(default=None, pattern=rf"^({PARTY_ROLES})$")
    party_type: str | None = Field(default=None, pattern=rf"^({PARTY_TYPES})$")
    party_id: UUID | None = None
    display_name: str | None = Field(default=None, max_length=500)
    is_primary: bool | None = None
    contact_details: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class ContractPartyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    contract_id: UUID
    party_role: str
    party_type: str
    party_id: UUID | None = None
    display_name: str
    # Live name resolved by the service from the linked contact / subcontractor
    # / user. None when the link is missing or unresolved; the UI then falls
    # back to ``display_name``.
    resolved_name: str | None = None
    is_primary: bool
    contact_details: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# == ContractSecurity (bonds / guarantees / insurance) =====================


SECURITY_TYPES = (
    "performance_bond|payment_bond|advance_payment_bond|retention_bond|"
    "parent_company_guarantee|bank_guarantee|insurance_pl|insurance_car|"
    "insurance_pi|other"
)
SECURITY_STATUSES = "required|received|active|expired|released|claimed"


class ContractSecurityCreate(BaseModel):
    """Create a bond / guarantee / insurance record on a contract."""

    model_config = ConfigDict(str_strip_whitespace=True)

    contract_id: UUID
    security_type: str = Field(default="other", pattern=rf"^({SECURITY_TYPES})$")
    reference: str | None = Field(default=None, max_length=120)
    provider_name: str = Field(default="", max_length=255)
    amount: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="", max_length=3)
    percent_of_contract: Decimal | None = Field(default=None, ge=0, le=100)
    valid_from: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    valid_to: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    status: str = Field(default="required", pattern=rf"^({SECURITY_STATUSES})$")
    document_id: UUID | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContractSecurityUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    security_type: str | None = Field(default=None, pattern=rf"^({SECURITY_TYPES})$")
    reference: str | None = Field(default=None, max_length=120)
    provider_name: str | None = Field(default=None, max_length=255)
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    percent_of_contract: Decimal | None = Field(default=None, ge=0, le=100)
    valid_from: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    valid_to: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    status: str | None = Field(default=None, pattern=rf"^({SECURITY_STATUSES})$")
    document_id: UUID | None = None
    notes: str | None = None
    metadata: dict[str, Any] | None = None


class ContractSecurityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    contract_id: UUID
    security_type: str
    reference: str | None = None
    provider_name: str
    amount: Decimal
    currency: str
    percent_of_contract: Decimal | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    status: str
    document_id: UUID | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# == EOTClaim (extension-of-time claims) ===================================


EOT_STATUSES = "draft|submitted|under_review|granted|partially_granted|rejected|withdrawn"
# Statuses that represent a final decision on an EOT claim.
EOT_DECISIONS = "granted|partially_granted|rejected"


class EOTClaimCreate(BaseModel):
    """Create an extension-of-time claim (always starts in ``draft``)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    contract_id: UUID
    eot_number: str | None = Field(default=None, max_length=40)
    cause_category: str = Field(default="other", max_length=80)
    description: str = Field(default="", max_length=4000)
    days_claimed: int = Field(default=0, ge=0)
    claim_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    linked_delay_event_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EOTClaimUpdate(BaseModel):
    """Partial update for an EOT claim.

    Status changes are driven only by the dedicated submit / decide / withdraw
    endpoints (FSM + event emission), so ``status``, ``days_granted`` and the
    decision fields are intentionally not editable here.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    eot_number: str | None = Field(default=None, max_length=40)
    cause_category: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=4000)
    days_claimed: int | None = Field(default=None, ge=0)
    claim_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    linked_delay_event_id: UUID | None = None
    metadata: dict[str, Any] | None = None


class EOTDecisionRequest(BaseModel):
    """Body for ``POST /eot-claims/{id}/decide``.

    ``decision`` is the target status (granted / partially_granted / rejected).
    ``days_granted`` is clamped server-side to ``[0, days_claimed]`` so a
    decision can never grant more time than was claimed. A rejected claim
    grants zero days regardless of the supplied value.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    decision: str = Field(..., pattern=rf"^({EOT_DECISIONS})$")
    days_granted: int = Field(default=0, ge=0)
    decision_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    revised_completion_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class EOTClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    contract_id: UUID
    eot_number: str
    cause_category: str
    description: str
    days_claimed: int
    days_granted: int
    claim_date: str | None = None
    decision_date: str | None = None
    status: str
    revised_completion_date: str | None = None
    linked_delay_event_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# == ContractDocument (documents register) =================================


DOC_ROLES = "executed_agreement|drawing|specification|bond|insurance|correspondence|variation|other"


class ContractDocumentCreate(BaseModel):
    """Register a document against a contract."""

    model_config = ConfigDict(str_strip_whitespace=True)

    contract_id: UUID
    document_id: UUID | None = None
    doc_role: str = Field(default="other", pattern=rf"^({DOC_ROLES})$")
    title: str = Field(default="", max_length=500)
    version: str = Field(default="", max_length=40)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContractDocumentUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    document_id: UUID | None = None
    doc_role: str | None = Field(default=None, pattern=rf"^({DOC_ROLES})$")
    title: str | None = Field(default=None, max_length=500)
    version: str | None = Field(default=None, max_length=40)
    metadata: dict[str, Any] | None = None


class ContractDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    contract_id: UUID
    document_id: UUID | None = None
    doc_role: str
    title: str
    version: str
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# == ContractMilestone (milestones / payment schedule) =====================


MILESTONE_TRIGGERS = "date|completion|approval"
MILESTONE_STATUSES = "pending|reached|invoiced|paid"


class ContractMilestoneCreate(BaseModel):
    """Create a contract milestone / payment-schedule entry."""

    model_config = ConfigDict(str_strip_whitespace=True)

    contract_id: UUID
    code: str = Field(default="", max_length=80)
    name: str = Field(default="", max_length=500)
    planned_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    value: Decimal | None = None
    percent_of_contract: Decimal | None = Field(default=None, ge=0, le=100)
    trigger: str = Field(default="date", pattern=rf"^({MILESTONE_TRIGGERS})$")
    status: str = Field(default="pending", pattern=rf"^({MILESTONE_STATUSES})$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContractMilestoneUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    code: str | None = Field(default=None, max_length=80)
    name: str | None = Field(default=None, max_length=500)
    planned_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    value: Decimal | None = None
    percent_of_contract: Decimal | None = Field(default=None, ge=0, le=100)
    trigger: str | None = Field(default=None, pattern=rf"^({MILESTONE_TRIGGERS})$")
    status: str | None = Field(default=None, pattern=rf"^({MILESTONE_STATUSES})$")
    metadata: dict[str, Any] | None = None


class ContractMilestoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    contract_id: UUID
    code: str
    name: str
    planned_date: str | None = None
    value: Decimal | None = None
    percent_of_contract: Decimal | None = None
    trigger: str
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# Final-account readiness checklist (close-out conditions) ==================


class FinalAccountCheckItemResponse(BaseModel):
    """One close-out condition in the final-account readiness checklist."""

    key: str
    status: str
    reason: str
    based_on: dict[str, str] = Field(default_factory=dict)


class FinalAccountChecklistResponse(BaseModel):
    """Final-account (close-out) readiness checklist for a contract.

    Each item is a close-out condition evaluated from data the contract already
    stores. ``ready`` is true only when every applicable check passed and at
    least one applies; ``completion_percent`` counts passed over applicable
    checks (not-applicable checks excluded), guarded against a zero divisor.
    """

    contract_id: UUID
    ready: bool
    completion_percent: Decimal
    passed_count: int
    applicable_count: int
    total_count: int
    items: list[FinalAccountCheckItemResponse] = Field(default_factory=list)
