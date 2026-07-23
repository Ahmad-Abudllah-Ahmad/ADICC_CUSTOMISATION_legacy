"""v0.9.0 -- add all new module tables.

Creates tables for modules added since the initial baseline:
i18n_foundation, contacts, correspondence, changeorders, costmodel, finance,
inspections, meetings, ncr, punchlist, fieldreports, submittals, transmittals,
procurement, requirements, notifications, bim_hub, markups, cde, risk, safety,
enterprise_workflows, full_evm, rfq_bidding, and the core audit log.

Uses CREATE TABLE IF NOT EXISTS for idempotent execution on databases where
SQLAlchemy auto-create has already created these tables (typical in dev with
SQLite).  For adding columns to existing tables, uses try/except to gracefully
handle the case where columns already exist.

Revision ID: v090_new_modules
Revises: 129188e46db8
Create Date: 2026-04-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v090_new_modules"
down_revision: Union[str, None] = "129188e46db8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_if_not_exists(table_name: str, *columns: sa.Column, **kw) -> None:  # noqa: ANN003
    """Create a table only if it does not already exist.

    For SQLite (dev) tables are auto-created by ``Base.metadata.create_all``.
    For PostgreSQL (production) this migration is the canonical DDL source.
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table_name not in insp.get_table_names():
        op.create_table(table_name, *columns, **kw)


def _add_column_safe(table_name: str, column: sa.Column) -> None:
    """Add a column to *table_name*, silently skipping if it already exists."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = [c["name"] for c in insp.get_columns(table_name)]
    if column.name not in existing:
        op.add_column(table_name, column)


# ---------------------------------------------------------------------------
# Common column fragments
# ---------------------------------------------------------------------------


def _pk() -> sa.Column:
    return sa.Column("id", sa.String(36), primary_key=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _meta() -> sa.Column:
    return sa.Column("metadata", sa.JSON, nullable=False, server_default="{}")


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # ── i18n_foundation ──────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_i18n_exchange_rate",
        _pk(),
        sa.Column("from_currency", sa.String(10), nullable=False, index=True),
        sa.Column("to_currency", sa.String(10), nullable=False, index=True),
        sa.Column("rate", sa.String(50), nullable=False),
        sa.Column("rate_date", sa.String(20), nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("is_manual", sa.Boolean, nullable=False, server_default=sa.text("true")),
        _meta(),
        *_timestamps(),
        sa.UniqueConstraint("from_currency", "to_currency", "rate_date", name="uq_exchange_rate_pair_date"),
    )

    _create_if_not_exists(
        "oe_i18n_country",
        _pk(),
        sa.Column("iso_code", sa.String(2), unique=True, index=True, nullable=False),
        sa.Column("iso_code_3", sa.String(3), nullable=True),
        sa.Column("name_en", sa.String(255), nullable=False),
        sa.Column("name_translations", sa.JSON, nullable=False),
        sa.Column("currency_default", sa.String(10), nullable=True),
        sa.Column("measurement_default", sa.String(20), nullable=True),
        sa.Column("phone_code", sa.String(10), nullable=True),
        sa.Column("address_format_template", sa.JSON, nullable=True),
        sa.Column("region_group", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_i18n_work_calendar",
        _pk(),
        sa.Column("country_code", sa.String(2), index=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_translations", sa.JSON, nullable=True),
        sa.Column("year", sa.String(4), nullable=False),
        sa.Column("work_hours_per_day", sa.String(10), nullable=False, server_default="8"),
        sa.Column("work_days", sa.JSON, nullable=False),
        sa.Column("exceptions", sa.JSON, nullable=False),
        _meta(),
        *_timestamps(),
        sa.UniqueConstraint("country_code", "year", name="uq_work_calendar_country_year"),
    )

    _create_if_not_exists(
        "oe_i18n_tax_config",
        _pk(),
        sa.Column("country_code", sa.String(2), index=True, nullable=False),
        sa.Column("tax_name", sa.String(255), nullable=False),
        sa.Column("tax_name_translations", sa.JSON, nullable=True),
        sa.Column("tax_code", sa.String(50), nullable=True),
        sa.Column("rate_pct", sa.String(20), nullable=False),
        sa.Column("tax_type", sa.String(50), nullable=False),
        sa.Column("effective_from", sa.String(20), nullable=True),
        sa.Column("effective_to", sa.String(20), nullable=True),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.text("false")),
        _meta(),
        *_timestamps(),
        sa.Index("ix_tax_config_country_type", "country_code", "tax_type"),
    )

    # ── contacts ─────────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_contacts_contact",
        _pk(),
        sa.Column("contact_type", sa.String(50), nullable=False),
        sa.Column("is_platform_user", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("user_id", sa.String(36), nullable=True, index=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("last_name", sa.String(255), nullable=True),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("legal_name", sa.String(255), nullable=True),
        sa.Column("vat_number", sa.String(50), nullable=True),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column("address", sa.JSON, nullable=True),
        sa.Column("primary_email", sa.String(255), nullable=True, index=True),
        sa.Column("primary_phone", sa.String(50), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("certifications", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("insurance", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("prequalification_status", sa.String(50), nullable=True),
        sa.Column("qualified_until", sa.String(20), nullable=True),
        sa.Column("payment_terms_days", sa.String(10), nullable=True),
        sa.Column("currency_code", sa.String(10), nullable=True),
        sa.Column("name_translations", sa.JSON, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    # ── correspondence ───────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_correspondence_correspondence",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("reference_number", sa.String(50), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("from_contact_id", sa.String(36), nullable=True),
        sa.Column("to_contact_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("date_sent", sa.String(20), nullable=True),
        sa.Column("date_received", sa.String(20), nullable=True),
        sa.Column("correspondence_type", sa.String(50), nullable=False),
        sa.Column("linked_document_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("linked_transmittal_id", sa.String(36), nullable=True),
        sa.Column("linked_rfi_id", sa.String(36), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    # ── changeorders ─────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_changeorders_order",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("reason_category", sa.String(50), nullable=False, server_default="client_request"),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("submitted_by", sa.String(36), nullable=True),
        sa.Column("approved_by", sa.String(36), nullable=True),
        sa.Column("submitted_at", sa.String(20), nullable=True),
        sa.Column("approved_at", sa.String(20), nullable=True),
        sa.Column("cost_impact", sa.String(50), nullable=False, server_default="0"),
        sa.Column("schedule_impact_days", sa.Integer, nullable=False, server_default="0"),
        sa.Column("currency", sa.String(10), nullable=False, server_default="EUR"),
        sa.Column("variation_type", sa.String(50), nullable=True),
        sa.Column("cost_basis", sa.String(50), nullable=True),
        sa.Column("contractor_submission_date", sa.String(20), nullable=True),
        sa.Column("contractor_amount", sa.String(50), nullable=True),
        sa.Column("engineer_amount", sa.String(50), nullable=True),
        sa.Column("approved_amount", sa.String(50), nullable=True),
        sa.Column("time_impact_days", sa.Integer, nullable=True),
        sa.Column("approved_time_days", sa.Integer, nullable=True),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_changeorders_item",
        _pk(),
        sa.Column(
            "change_order_id",
            sa.String(36),
            sa.ForeignKey("oe_changeorders_order.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("change_type", sa.String(50), nullable=False, server_default="modified"),
        sa.Column("original_quantity", sa.String(50), nullable=False, server_default="0"),
        sa.Column("new_quantity", sa.String(50), nullable=False, server_default="0"),
        sa.Column("original_rate", sa.String(50), nullable=False, server_default="0"),
        sa.Column("new_rate", sa.String(50), nullable=False, server_default="0"),
        sa.Column("cost_delta", sa.String(50), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(20), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        _meta(),
        *_timestamps(),
    )

    # ── costmodel ────────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_costmodel_snapshot",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("period", sa.String(10), nullable=False),
        sa.Column("planned_cost", sa.String(50), nullable=False, server_default="0"),
        sa.Column("earned_value", sa.String(50), nullable=False, server_default="0"),
        sa.Column("actual_cost", sa.String(50), nullable=False, server_default="0"),
        sa.Column("forecast_eac", sa.String(50), nullable=False, server_default="0"),
        sa.Column("spi", sa.String(10), nullable=False, server_default="0"),
        sa.Column("cpi", sa.String(10), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_costmodel_budget_line",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("boq_position_id", sa.String(36), nullable=True, index=True),
        sa.Column("activity_id", sa.String(36), nullable=True),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("planned_amount", sa.String(50), nullable=False, server_default="0"),
        sa.Column("committed_amount", sa.String(50), nullable=False, server_default="0"),
        sa.Column("actual_amount", sa.String(50), nullable=False, server_default="0"),
        sa.Column("forecast_amount", sa.String(50), nullable=False, server_default="0"),
        sa.Column("period_start", sa.String(20), nullable=True),
        sa.Column("period_end", sa.String(20), nullable=True),
        sa.Column("currency", sa.String(10), nullable=False, server_default=""),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_costmodel_cash_flow",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("period", sa.String(10), nullable=False),
        sa.Column("category", sa.String(100), nullable=False, server_default="total"),
        sa.Column("planned_inflow", sa.String(50), nullable=False, server_default="0"),
        sa.Column("planned_outflow", sa.String(50), nullable=False, server_default="0"),
        sa.Column("actual_inflow", sa.String(50), nullable=False, server_default="0"),
        sa.Column("actual_outflow", sa.String(50), nullable=False, server_default="0"),
        sa.Column("cumulative_planned", sa.String(50), nullable=False, server_default="0"),
        sa.Column("cumulative_actual", sa.String(50), nullable=False, server_default="0"),
        _meta(),
        *_timestamps(),
    )

    # ── finance ──────────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_finance_invoice",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("contact_id", sa.String(36), nullable=True),
        sa.Column("invoice_direction", sa.String(20), nullable=False),
        sa.Column("invoice_number", sa.String(50), nullable=False),
        sa.Column("invoice_date", sa.String(20), nullable=False),
        sa.Column("due_date", sa.String(20), nullable=True),
        sa.Column("currency_code", sa.String(10), nullable=False, server_default="EUR"),
        sa.Column("amount_subtotal", sa.String(50), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.String(50), nullable=False, server_default="0"),
        sa.Column("retention_amount", sa.String(50), nullable=False, server_default="0"),
        sa.Column("amount_total", sa.String(50), nullable=False, server_default="0"),
        sa.Column("tax_config_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("payment_terms_days", sa.String(10), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_finance_invoice_item",
        _pk(),
        sa.Column(
            "invoice_id", sa.String(36), sa.ForeignKey("oe_finance_invoice.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.String(50), nullable=False, server_default="1"),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("unit_rate", sa.String(50), nullable=False, server_default="0"),
        sa.Column("amount", sa.String(50), nullable=False, server_default="0"),
        sa.Column("wbs_id", sa.String(36), nullable=True),
        sa.Column("cost_category", sa.String(100), nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_finance_payment",
        _pk(),
        sa.Column(
            "invoice_id", sa.String(36), sa.ForeignKey("oe_finance_invoice.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("payment_date", sa.String(20), nullable=False),
        sa.Column("amount", sa.String(50), nullable=False),
        sa.Column("currency_code", sa.String(10), nullable=False, server_default="EUR"),
        sa.Column("exchange_rate_snapshot", sa.String(50), nullable=False, server_default="1"),
        sa.Column("reference", sa.String(255), nullable=True),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_finance_budget",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("wbs_id", sa.String(36), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("original_budget", sa.String(50), nullable=False, server_default="0"),
        sa.Column("revised_budget", sa.String(50), nullable=False, server_default="0"),
        sa.Column("committed", sa.String(50), nullable=False, server_default="0"),
        sa.Column("actual", sa.String(50), nullable=False, server_default="0"),
        sa.Column("forecast_final", sa.String(50), nullable=False, server_default="0"),
        _meta(),
        *_timestamps(),
        sa.UniqueConstraint("project_id", "wbs_id", "category", name="uq_finance_budget_proj_wbs_cat"),
    )

    _create_if_not_exists(
        "oe_finance_evm_snapshot",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("snapshot_date", sa.String(20), nullable=False),
        sa.Column("bac", sa.String(50), nullable=False, server_default="0"),
        sa.Column("pv", sa.String(50), nullable=False, server_default="0"),
        sa.Column("ev", sa.String(50), nullable=False, server_default="0"),
        sa.Column("ac", sa.String(50), nullable=False, server_default="0"),
        sa.Column("sv", sa.String(50), nullable=False, server_default="0"),
        sa.Column("cv", sa.String(50), nullable=False, server_default="0"),
        sa.Column("spi", sa.String(50), nullable=False, server_default="0"),
        sa.Column("cpi", sa.String(50), nullable=False, server_default="0"),
        _meta(),
        *_timestamps(),
    )

    # ── rfi ──────────────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_rfi_rfi",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("rfi_number", sa.String(20), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("raised_by", sa.String(36), nullable=False),
        sa.Column("assigned_to", sa.String(36), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("ball_in_court", sa.String(36), nullable=True),
        sa.Column("official_response", sa.Text, nullable=True),
        sa.Column("responded_by", sa.String(36), nullable=True),
        sa.Column("responded_at", sa.String(20), nullable=True),
        sa.Column("cost_impact", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("cost_impact_value", sa.String(50), nullable=True),
        sa.Column("schedule_impact", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("schedule_impact_days", sa.Integer, nullable=True),
        sa.Column("date_required", sa.String(20), nullable=True),
        sa.Column("response_due_date", sa.String(20), nullable=True),
        sa.Column("linked_drawing_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("change_order_id", sa.String(36), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    # ── risk ─────────────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_risk_register",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("category", sa.String(50), nullable=False, server_default="technical"),
        sa.Column("probability", sa.String(10), nullable=False, server_default="0.5"),
        sa.Column("impact_cost", sa.String(50), nullable=False, server_default="0"),
        sa.Column("impact_schedule_days", sa.Integer, nullable=False, server_default="0"),
        sa.Column("impact_severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("risk_score", sa.String(10), nullable=False, server_default="0"),
        sa.Column("status", sa.String(50), nullable=False, server_default="identified"),
        sa.Column("mitigation_strategy", sa.Text, nullable=False, server_default=""),
        sa.Column("contingency_plan", sa.Text, nullable=False, server_default=""),
        sa.Column("owner_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("response_cost", sa.String(50), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(10), nullable=False, server_default="EUR"),
        sa.Column("probability_score", sa.Integer, nullable=True),
        sa.Column("impact_score_cost", sa.Integer, nullable=True),
        sa.Column("impact_score_time", sa.Integer, nullable=True),
        sa.Column("risk_tier", sa.String(20), nullable=True),
        sa.Column("mitigation_actions", sa.JSON, nullable=True),
        _meta(),
        *_timestamps(),
    )

    # ── safety ───────────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_safety_incident",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("incident_number", sa.String(20), nullable=False),
        sa.Column("incident_date", sa.String(20), nullable=False),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("incident_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("injured_person_details", sa.JSON, nullable=True),
        sa.Column("treatment_type", sa.String(50), nullable=True),
        sa.Column("days_lost", sa.Integer, nullable=False, server_default="0"),
        sa.Column("root_cause", sa.Text, nullable=True),
        sa.Column("corrective_actions", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("reported_to_regulator", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(50), nullable=False, server_default="reported"),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_safety_observation",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("observation_number", sa.String(20), nullable=False),
        sa.Column("observation_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("severity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("likelihood", sa.Integer, nullable=False, server_default="1"),
        sa.Column("risk_score", sa.Integer, nullable=False, server_default="1"),
        sa.Column("immediate_action", sa.Text, nullable=True),
        sa.Column("corrective_action", sa.Text, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    # ── inspections ──────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_inspections_inspection",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("inspection_number", sa.String(20), nullable=False),
        sa.Column("inspection_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("wbs_id", sa.String(36), nullable=True),
        sa.Column("inspector_id", sa.String(36), nullable=True),
        sa.Column("inspection_date", sa.String(20), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="scheduled"),
        sa.Column("result", sa.String(50), nullable=True),
        sa.Column("checklist_data", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    # ── meetings ─────────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_meetings_meeting",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("meeting_number", sa.String(20), nullable=False),
        sa.Column("meeting_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("meeting_date", sa.String(20), nullable=False),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("chairperson_id", sa.String(36), nullable=True),
        sa.Column("attendees", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("agenda_items", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("action_items", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("minutes", sa.Text, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    # ── ncr ──────────────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_ncr_ncr",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("ncr_number", sa.String(20), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("ncr_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("root_cause", sa.Text, nullable=True),
        sa.Column("root_cause_category", sa.String(100), nullable=True),
        sa.Column("corrective_action", sa.Text, nullable=True),
        sa.Column("preventive_action", sa.Text, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="identified"),
        sa.Column("cost_impact", sa.String(50), nullable=True),
        sa.Column("schedule_impact_days", sa.Integer, nullable=True),
        sa.Column("location_description", sa.String(500), nullable=True),
        sa.Column("linked_inspection_id", sa.String(36), nullable=True),
        sa.Column("change_order_id", sa.String(36), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    # ── punchlist ────────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_punchlist_item",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("document_id", sa.String(36), nullable=True),
        sa.Column("page", sa.Integer, nullable=True),
        sa.Column("location_x", sa.Float, nullable=True),
        sa.Column("location_y", sa.Float, nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("assigned_to", sa.String(36), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("trade", sa.String(100), nullable=True),
        sa.Column("photos", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.String(36), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    # ── fieldreports ─────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_fieldreports_report",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("report_date", sa.Date, nullable=False, index=True),
        sa.Column("report_type", sa.String(30), nullable=False, server_default="daily"),
        sa.Column("weather_condition", sa.String(30), nullable=False, server_default="clear"),
        sa.Column("temperature_c", sa.Float, nullable=True),
        sa.Column("wind_speed", sa.String(50), nullable=True),
        sa.Column("precipitation", sa.String(100), nullable=True),
        sa.Column("humidity", sa.Integer, nullable=True),
        sa.Column("workforce", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("equipment_on_site", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("work_performed", sa.Text, nullable=False, server_default=""),
        sa.Column("delays", sa.Text, nullable=True),
        sa.Column("delay_hours", sa.Float, nullable=False, server_default="0"),
        sa.Column("visitors", sa.Text, nullable=True),
        sa.Column("deliveries", sa.Text, nullable=True),
        sa.Column("safety_incidents", sa.Text, nullable=True),
        sa.Column("materials_used", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("photos", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("workforce_log", sa.JSON, nullable=True),
        sa.Column("equipment_log", sa.JSON, nullable=True),
        sa.Column("weather_data", sa.JSON, nullable=True),
        sa.Column("signature_by", sa.String(255), nullable=True),
        sa.Column("signature_data", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("approved_by", sa.String(36), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_fieldreports_workforce",
        _pk(),
        sa.Column(
            "field_report_id",
            sa.String(36),
            sa.ForeignKey("oe_fieldreports_report.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("worker_type", sa.String(100), nullable=False),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("headcount", sa.Integer, nullable=False, server_default="0"),
        sa.Column("hours_worked", sa.String(10), nullable=False, server_default="0"),
        sa.Column("overtime_hours", sa.String(10), nullable=False, server_default="0"),
        sa.Column("wbs_id", sa.String(36), nullable=True),
        sa.Column("cost_category", sa.String(100), nullable=True),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_fieldreports_equipment",
        _pk(),
        sa.Column(
            "field_report_id",
            sa.String(36),
            sa.ForeignKey("oe_fieldreports_report.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("equipment_description", sa.String(500), nullable=False),
        sa.Column("equipment_type", sa.String(100), nullable=True),
        sa.Column("hours_operational", sa.String(10), nullable=False, server_default="0"),
        sa.Column("hours_standby", sa.String(10), nullable=False, server_default="0"),
        sa.Column("hours_breakdown", sa.String(10), nullable=False, server_default="0"),
        sa.Column("operator_name", sa.String(255), nullable=True),
        _meta(),
        *_timestamps(),
    )

    # ── submittals ───────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_submittals_submittal",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("submittal_number", sa.String(20), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("spec_section", sa.String(100), nullable=True),
        sa.Column("submittal_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("ball_in_court", sa.String(36), nullable=True),
        sa.Column("current_revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("submitted_by_org", sa.String(36), nullable=True),
        sa.Column("reviewer_id", sa.String(36), nullable=True),
        sa.Column("approver_id", sa.String(36), nullable=True),
        sa.Column("date_submitted", sa.String(20), nullable=True),
        sa.Column("date_required", sa.String(20), nullable=True),
        sa.Column("date_returned", sa.String(20), nullable=True),
        sa.Column("linked_boq_item_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    # ── transmittals ─────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_transmittals_transmittal",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("transmittal_number", sa.String(50), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("sender_org_id", sa.String(36), nullable=True),
        sa.Column("purpose_code", sa.String(50), nullable=False),
        sa.Column("issued_date", sa.String(20), nullable=True),
        sa.Column("response_due_date", sa.String(20), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("cover_note", sa.Text, nullable=True),
        sa.Column("is_locked", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_transmittals_recipient",
        _pk(),
        sa.Column(
            "transmittal_id",
            sa.String(36),
            sa.ForeignKey("oe_transmittals_transmittal.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("recipient_org_id", sa.String(36), nullable=True),
        sa.Column("recipient_user_id", sa.String(36), nullable=True),
        sa.Column("action_required", sa.String(100), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response", sa.Text, nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_transmittals_item",
        _pk(),
        sa.Column(
            "transmittal_id",
            sa.String(36),
            sa.ForeignKey("oe_transmittals_transmittal.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("document_id", sa.String(36), nullable=True),
        sa.Column("item_number", sa.Integer, nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        *_timestamps(),
    )

    # ── procurement ──────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_procurement_po",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("vendor_contact_id", sa.String(36), nullable=True),
        sa.Column("po_number", sa.String(50), nullable=False),
        sa.Column("po_type", sa.String(50), nullable=False, server_default="standard"),
        sa.Column("issue_date", sa.String(20), nullable=True),
        sa.Column("delivery_date", sa.String(20), nullable=True),
        sa.Column("currency_code", sa.String(10), nullable=False, server_default="EUR"),
        sa.Column("amount_subtotal", sa.String(50), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.String(50), nullable=False, server_default="0"),
        sa.Column("amount_total", sa.String(50), nullable=False, server_default="0"),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("payment_terms", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_procurement_po_item",
        _pk(),
        sa.Column("po_id", sa.String(36), sa.ForeignKey("oe_procurement_po.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.String(50), nullable=False, server_default="1"),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("unit_rate", sa.String(50), nullable=False, server_default="0"),
        sa.Column("amount", sa.String(50), nullable=False, server_default="0"),
        sa.Column("wbs_id", sa.String(36), nullable=True),
        sa.Column("cost_category", sa.String(100), nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_procurement_goods_receipt",
        _pk(),
        sa.Column("po_id", sa.String(36), sa.ForeignKey("oe_procurement_po.id", ondelete="CASCADE"), nullable=False),
        sa.Column("receipt_date", sa.String(20), nullable=False),
        sa.Column("received_by_id", sa.String(36), nullable=True),
        sa.Column("delivery_note_number", sa.String(100), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text, nullable=True),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_procurement_gr_item",
        _pk(),
        sa.Column(
            "receipt_id",
            sa.String(36),
            sa.ForeignKey("oe_procurement_goods_receipt.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("po_item_id", sa.String(36), nullable=True),
        sa.Column("quantity_ordered", sa.String(50), nullable=False, server_default="0"),
        sa.Column("quantity_received", sa.String(50), nullable=False, server_default="0"),
        sa.Column("quantity_rejected", sa.String(50), nullable=False, server_default="0"),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        *_timestamps(),
    )

    # ── requirements ─────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_requirements_set",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("source_type", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("source_filename", sa.String(500), nullable=False, server_default=""),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("gate_status", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(36), nullable=False, server_default=""),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_requirements_item",
        _pk(),
        sa.Column(
            "requirement_set_id",
            sa.String(36),
            sa.ForeignKey("oe_requirements_set.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("entity", sa.String(255), nullable=False),
        sa.Column("attribute", sa.String(255), nullable=False),
        sa.Column("constraint_type", sa.String(50), nullable=False, server_default="equals"),
        sa.Column("constraint_value", sa.String(500), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False, server_default=""),
        sa.Column("category", sa.String(100), nullable=False, server_default="general"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="must"),
        sa.Column("confidence", sa.String(10), nullable=True),
        sa.Column("source_ref", sa.String(500), nullable=False, server_default=""),
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),
        sa.Column("linked_position_id", sa.String(36), nullable=True, index=True),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("created_by", sa.String(36), nullable=False, server_default=""),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_requirements_gate_result",
        _pk(),
        sa.Column(
            "requirement_set_id",
            sa.String(36),
            sa.ForeignKey("oe_requirements_set.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("gate_number", sa.Integer, nullable=False),
        sa.Column("gate_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="skipped"),
        sa.Column("score", sa.String(10), nullable=False, server_default="0"),
        sa.Column("findings", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("executed_by", sa.String(36), nullable=False, server_default=""),
        *_timestamps(),
    )

    # ── notifications ────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_notifications_notification",
        _pk(),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("notification_type", sa.String(100), nullable=False, index=True),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("title_key", sa.String(255), nullable=False),
        sa.Column("body_key", sa.String(255), nullable=True),
        sa.Column("body_context", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("action_url", sa.String(500), nullable=True),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        _meta(),
        *_timestamps(),
    )

    # ── bim_hub ──────────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_bim_model",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("discipline", sa.String(50), nullable=True),
        sa.Column("model_format", sa.String(20), nullable=True),
        sa.Column("version", sa.String(20), nullable=False, server_default="1"),
        sa.Column("import_date", sa.String(20), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="processing"),
        sa.Column("element_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("storey_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("bounding_box", sa.JSON, nullable=True),
        sa.Column("original_file_id", sa.String(36), nullable=True),
        sa.Column("canonical_file_path", sa.String(500), nullable=True),
        sa.Column("parent_model_id", sa.String(36), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_bim_element",
        _pk(),
        sa.Column(
            "model_id", sa.String(36), sa.ForeignKey("oe_bim_model.id", ondelete="CASCADE"), nullable=False, index=True
        ),
        sa.Column("stable_id", sa.String(255), nullable=False),
        sa.Column("element_type", sa.String(100), nullable=True),
        sa.Column("name", sa.String(500), nullable=True),
        sa.Column("storey", sa.String(255), nullable=True),
        sa.Column("discipline", sa.String(50), nullable=True),
        sa.Column("properties", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("quantities", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("geometry_hash", sa.String(64), nullable=True),
        sa.Column("bounding_box", sa.JSON, nullable=True),
        sa.Column("mesh_ref", sa.String(500), nullable=True),
        sa.Column("lod_variants", sa.JSON, nullable=True),
        _meta(),
        *_timestamps(),
        sa.Index("ix_bim_element_model_stable", "model_id", "stable_id"),
    )

    _create_if_not_exists(
        "oe_bim_boq_link",
        _pk(),
        sa.Column("boq_position_id", sa.String(36), nullable=False, index=True),
        sa.Column(
            "bim_element_id",
            sa.String(36),
            sa.ForeignKey("oe_bim_element.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("link_type", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("confidence", sa.String(10), nullable=True),
        sa.Column("rule_id", sa.String(100), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
        sa.UniqueConstraint("boq_position_id", "bim_element_id", name="uq_bim_boq_link_pos_elem"),
    )

    _create_if_not_exists(
        "oe_bim_quantity_map",
        _pk(),
        sa.Column("org_id", sa.String(36), nullable=True),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_translations", sa.JSON, nullable=True),
        sa.Column("element_type_filter", sa.String(100), nullable=True),
        sa.Column("property_filter", sa.JSON, nullable=True),
        sa.Column("quantity_source", sa.String(100), nullable=False),
        sa.Column("multiplier", sa.String(20), nullable=False, server_default="1"),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("waste_factor_pct", sa.String(10), nullable=False, server_default="0"),
        sa.Column("boq_target", sa.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_bim_model_diff",
        _pk(),
        sa.Column("old_model_id", sa.String(36), sa.ForeignKey("oe_bim_model.id", ondelete="CASCADE"), nullable=False),
        sa.Column("new_model_id", sa.String(36), sa.ForeignKey("oe_bim_model.id", ondelete="CASCADE"), nullable=False),
        sa.Column("diff_summary", sa.JSON, nullable=False),
        sa.Column("diff_details", sa.JSON, nullable=True),
        _meta(),
        *_timestamps(),
        sa.UniqueConstraint("old_model_id", "new_model_id", name="uq_bim_model_diff_pair"),
    )

    # ── markups ──────────────────────────────────────────────────────────

    # StampTemplate must be created before Markup (FK dependency)
    _create_if_not_exists(
        "oe_markups_stamp_template",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=True, index=True),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=False, server_default="custom"),
        sa.Column("text", sa.String(500), nullable=False),
        sa.Column("color", sa.String(20), nullable=False, server_default="#22c55e"),
        sa.Column("background_color", sa.String(20), nullable=True),
        sa.Column("icon", sa.String(100), nullable=True),
        sa.Column("include_date", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("include_name", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_markups_markup",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("document_id", sa.String(255), nullable=True, index=True),
        sa.Column("page", sa.Integer, nullable=False, server_default="1"),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("geometry", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("text", sa.Text, nullable=True),
        sa.Column("color", sa.String(20), nullable=False, server_default="#3b82f6"),
        sa.Column("line_width", sa.Integer, nullable=False, server_default="2"),
        sa.Column("opacity", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("author_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("measurement_value", sa.Float, nullable=True),
        sa.Column("measurement_unit", sa.String(20), nullable=True),
        sa.Column("stamp_template_id", sa.String(36), nullable=True),
        sa.Column("linked_boq_position_id", sa.String(255), nullable=True),
        _meta(),
        sa.Column("created_by", sa.String(255), nullable=False, server_default=""),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_markups_scale_config",
        _pk(),
        sa.Column("document_id", sa.String(255), nullable=False, index=True),
        sa.Column("page", sa.Integer, nullable=False, server_default="1"),
        sa.Column("pixels_per_unit", sa.Float, nullable=False),
        sa.Column("unit_label", sa.String(20), nullable=False, server_default="m"),
        sa.Column("calibration_points", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("real_distance", sa.Float, nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False, server_default=""),
        *_timestamps(),
    )

    # ── cde ──────────────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_cde_container",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("container_code", sa.String(255), nullable=False),
        sa.Column("originator_code", sa.String(50), nullable=True),
        sa.Column("functional_breakdown", sa.String(50), nullable=True),
        sa.Column("spatial_breakdown", sa.String(50), nullable=True),
        sa.Column("form_code", sa.String(50), nullable=True),
        sa.Column("discipline_code", sa.String(50), nullable=True),
        sa.Column("sequence_number", sa.String(20), nullable=True),
        sa.Column("classification_system", sa.String(50), nullable=True),
        sa.Column("classification_code", sa.String(50), nullable=True),
        sa.Column("cde_state", sa.String(50), nullable=False, server_default="wip"),
        sa.Column("suitability_code", sa.String(10), nullable=True),
        sa.Column("current_revision_id", sa.String(36), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("security_classification", sa.String(50), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_cde_revision",
        _pk(),
        sa.Column(
            "container_id",
            sa.String(36),
            sa.ForeignKey("oe_cde_container.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("revision_code", sa.String(20), nullable=False),
        sa.Column("revision_number", sa.Integer, nullable=False),
        sa.Column("is_preliminary", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("file_size", sa.String(20), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("storage_key", sa.String(500), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("approved_by", sa.String(36), nullable=True),
        sa.Column("change_summary", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    # ── enterprise_workflows ─────────────────────────────────────────────

    _create_if_not_exists(
        "oe_workflows_approval",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=True, index=True),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("steps", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_workflows_request",
        _pk(),
        sa.Column(
            "workflow_id", sa.String(36), sa.ForeignKey("oe_workflows_approval.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("current_step", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("decided_by", sa.String(36), nullable=True),
        sa.Column("decided_at", sa.String(20), nullable=True),
        sa.Column("decision_notes", sa.Text, nullable=True),
        _meta(),
        *_timestamps(),
    )

    # ── full_evm ─────────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_evm_forecast",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("forecast_date", sa.String(20), nullable=False),
        sa.Column("etc", sa.String(50), nullable=False, server_default="0"),
        sa.Column("eac", sa.String(50), nullable=False, server_default="0"),
        sa.Column("vac", sa.String(50), nullable=False, server_default="0"),
        sa.Column("tcpi", sa.String(50), nullable=False, server_default="0"),
        sa.Column("forecast_method", sa.String(50), nullable=False, server_default="cpi"),
        sa.Column("confidence_range_low", sa.String(50), nullable=True),
        sa.Column("confidence_range_high", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        _meta(),
        *_timestamps(),
    )

    # ── rfq_bidding ──────────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_rfq_rfq",
        _pk(),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("rfq_number", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("scope_of_work", sa.Text, nullable=True),
        sa.Column("submission_deadline", sa.String(20), nullable=True),
        sa.Column("currency_code", sa.String(10), nullable=False, server_default="EUR"),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("issued_to_contacts", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("created_by", sa.String(36), nullable=True),
        _meta(),
        *_timestamps(),
    )

    _create_if_not_exists(
        "oe_rfq_bid",
        _pk(),
        sa.Column("rfq_id", sa.String(36), sa.ForeignKey("oe_rfq_rfq.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bidder_contact_id", sa.String(36), nullable=False),
        sa.Column("bid_amount", sa.String(50), nullable=False),
        sa.Column("currency_code", sa.String(10), nullable=False, server_default="EUR"),
        sa.Column("submitted_at", sa.String(20), nullable=True),
        sa.Column("validity_days", sa.Integer, nullable=False, server_default="30"),
        sa.Column("technical_score", sa.String(10), nullable=True),
        sa.Column("commercial_score", sa.String(10), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_awarded", sa.Boolean, nullable=False, server_default=sa.text("false")),
        _meta(),
        *_timestamps(),
    )

    # ── core audit log ───────────────────────────────────────────────────

    _create_if_not_exists(
        "oe_core_audit_log",
        _pk(),
        sa.Column("action", sa.String(50), nullable=False, index=True),
        sa.Column("entity_type", sa.String(100), nullable=False, index=True),
        sa.Column("entity_id", sa.String(36), nullable=True, index=True),
        sa.Column("user_id", sa.String(36), nullable=True, index=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("details", sa.JSON, nullable=False, server_default="{}"),
        *_timestamps(),
    )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

_NEW_TABLES = [
    # Drop child tables before parents (reverse dependency order)
    "oe_core_audit_log",
    "oe_rfq_bid",
    "oe_rfq_rfq",
    "oe_evm_forecast",
    "oe_workflows_request",
    "oe_workflows_approval",
    "oe_cde_revision",
    "oe_cde_container",
    "oe_markups_scale_config",
    "oe_markups_markup",
    "oe_markups_stamp_template",
    "oe_bim_model_diff",
    "oe_bim_quantity_map",
    "oe_bim_boq_link",
    "oe_bim_element",
    "oe_bim_model",
    "oe_notifications_notification",
    "oe_requirements_gate_result",
    "oe_requirements_item",
    "oe_requirements_set",
    "oe_procurement_gr_item",
    "oe_procurement_goods_receipt",
    "oe_procurement_po_item",
    "oe_procurement_po",
    "oe_transmittals_item",
    "oe_transmittals_recipient",
    "oe_transmittals_transmittal",
    "oe_submittals_submittal",
    "oe_fieldreports_equipment",
    "oe_fieldreports_workforce",
    "oe_fieldreports_report",
    "oe_punchlist_item",
    "oe_ncr_ncr",
    "oe_meetings_meeting",
    "oe_inspections_inspection",
    "oe_safety_observation",
    "oe_safety_incident",
    "oe_risk_register",
    "oe_rfi_rfi",
    "oe_finance_evm_snapshot",
    "oe_finance_budget",
    "oe_finance_payment",
    "oe_finance_invoice_item",
    "oe_finance_invoice",
    "oe_costmodel_cash_flow",
    "oe_costmodel_budget_line",
    "oe_costmodel_snapshot",
    "oe_changeorders_item",
    "oe_changeorders_order",
    "oe_correspondence_correspondence",
    "oe_contacts_contact",
    "oe_i18n_tax_config",
    "oe_i18n_work_calendar",
    "oe_i18n_country",
    "oe_i18n_exchange_rate",
]


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = set(insp.get_table_names())
    for table in _NEW_TABLES:
        if table in existing:
            op.drop_table(table)
