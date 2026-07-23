# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""TOP-30 Wave 6 (job-cost depth) plus the leftover items.

Consolidated schema migration for the Wave 6 commercial/job-cost gaps and the
leftover features:

* Gap B - invoice line -> cost-spine link (oe_finance_invoice_item.cost_line_id)
* Gap C - equipment rental billing timestamp (oe_equipment_rental)
* Gap D - per-budget-line cost-overrun alert arming (oe_costmodel_budget_line)
* Gap E - certified-claim receivable + retainage withholding (oe_finance_invoice,
  oe_finance_payment)
* Gap F - PO retainage withholding + release ledger (oe_procurement_po,
  oe_procurement_po_retainage_release)
* #5  - cross-project resource leveling capacity (oe_resources_resource)
* #24 - risk auto-escalation flags (oe_risk_register)
* #20 - subcontractor monthly rating rollup table (oe_subcontractors_rating);
  the unique constraint was already added by v3158, this creates the table for
  external-PostgreSQL deployments where create_all did not run.

The embedded PostgreSQL runtime materialises all of this via create_all at
startup; this migration covers external-PostgreSQL deployments that manage
schema with Alembic. Every change is inspector-guarded so a re-run, or a DB the
runtime already auto-created, is a no-op. GUID columns are VARCHAR(36) (the
app.database.GUID TypeDecorator impl); sa.JSON() compiles to JSONB on
PostgreSQL via the codebase @compiles hook.

Revision ID: v3159_wave6_jobcost_leftover
Revises: v3158_subcontractor_scorecards
Create Date: 2026-06-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3159_wave6_jobcost_leftover"
down_revision = "v3158_subcontractor_scorecards"
branch_labels = None
depends_on = None


def _cols(insp: sa.Inspector, table: str) -> set[str]:
    try:
        return {c["name"] for c in insp.get_columns(table)}
    except Exception:  # noqa: BLE001 - table absent
        return set()


def _idx(insp: sa.Inspector, table: str) -> set[str]:
    try:
        return {ix["name"] for ix in insp.get_indexes(table)}
    except Exception:  # noqa: BLE001 - table absent
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    # ------------------------------------------------------------ Gap B finance
    ii = _cols(insp, "oe_finance_invoice_item")
    if ii and "cost_line_id" not in ii:
        op.add_column(
            "oe_finance_invoice_item",
            sa.Column("cost_line_id", sa.String(length=36), nullable=True),
        )
        if "ix_finance_invoice_item_cost_line_id" not in _idx(insp, "oe_finance_invoice_item"):
            op.create_index(
                "ix_finance_invoice_item_cost_line_id",
                "oe_finance_invoice_item",
                ["cost_line_id"],
            )

    # --------------------------------------------------------- Gap C equipment
    er = _cols(insp, "oe_equipment_rental")
    if er and "billing_calculated_at" not in er:
        op.add_column(
            "oe_equipment_rental",
            sa.Column("billing_calculated_at", sa.String(length=40), nullable=True),
        )

    # --------------------------------------------------------- Gap D costmodel
    bl = _cols(insp, "oe_costmodel_budget_line")
    if bl:
        if "overrun_alert_threshold_pct" not in bl:
            op.add_column(
                "oe_costmodel_budget_line",
                sa.Column(
                    "overrun_alert_threshold_pct",
                    sa.String(length=10),
                    nullable=False,
                    server_default="0",
                ),
            )
        if "overrun_alerted_at" not in bl:
            op.add_column(
                "oe_costmodel_budget_line",
                sa.Column("overrun_alerted_at", sa.DateTime(timezone=True), nullable=True),
            )
        if "ix_costmodel_budget_line_overrun_alert" not in _idx(insp, "oe_costmodel_budget_line"):
            op.create_index(
                "ix_costmodel_budget_line_overrun_alert",
                "oe_costmodel_budget_line",
                ["project_id", "overrun_alerted_at"],
                postgresql_where=sa.text("overrun_alert_threshold_pct > '0'"),
            )

    # ------------------------------------------------------------ Gap E finance
    inv = _cols(insp, "oe_finance_invoice")
    if inv and "source_claim_id" not in inv:
        op.add_column(
            "oe_finance_invoice",
            sa.Column("source_claim_id", sa.String(length=36), nullable=True),
        )
        if "ix_invoice_source_claim" not in _idx(insp, "oe_finance_invoice"):
            op.create_index("ix_invoice_source_claim", "oe_finance_invoice", ["source_claim_id"])

    pay = _cols(insp, "oe_finance_payment")
    if pay:
        if "withholding_amount" not in pay:
            op.add_column(
                "oe_finance_payment",
                sa.Column(
                    "withholding_amount",
                    sa.Numeric(18, 2),
                    nullable=False,
                    server_default="0",
                ),
            )
        if "source_claim_id" not in pay:
            op.add_column(
                "oe_finance_payment",
                sa.Column("source_claim_id", sa.String(length=36), nullable=True),
            )
            if "ix_finance_payment_source_claim" not in _idx(insp, "oe_finance_payment"):
                op.create_index(
                    "ix_finance_payment_source_claim",
                    "oe_finance_payment",
                    ["source_claim_id"],
                )
        if "withholding_release_date" not in pay:
            op.add_column(
                "oe_finance_payment",
                sa.Column("withholding_release_date", sa.String(length=40), nullable=True),
            )

    # --------------------------------------------------------- Gap F procurement
    po = _cols(insp, "oe_procurement_po")
    if po:
        if "retention_percent" not in po:
            op.add_column(
                "oe_procurement_po",
                sa.Column(
                    "retention_percent",
                    sa.Numeric(5, 2),
                    nullable=False,
                    server_default="0.00",
                ),
            )
        if "retain_on_receipt" not in po:
            op.add_column(
                "oe_procurement_po",
                sa.Column(
                    "retain_on_receipt",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            )
        if "retainage_released_amount" not in po:
            op.add_column(
                "oe_procurement_po",
                sa.Column(
                    "retainage_released_amount",
                    sa.String(length=50),
                    nullable=False,
                    server_default="0",
                ),
            )
        if "ix_po_retention_percent" not in _idx(insp, "oe_procurement_po"):
            op.create_index("ix_po_retention_percent", "oe_procurement_po", ["retention_percent"])

    if "oe_procurement_po_retainage_release" not in tables:
        op.create_table(
            "oe_procurement_po_retainage_release",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("po_id", sa.String(length=36), nullable=False),
            sa.Column("release_date", sa.String(length=40), nullable=False),
            sa.Column("release_amount", sa.Numeric(18, 4), nullable=False),
            sa.Column("release_reason", sa.String(length=255), nullable=True),
            sa.Column("released_by_id", sa.String(length=36), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(["po_id"], ["oe_procurement_po.id"], ondelete="CASCADE"),
        )
        op.create_index(
            "ix_retainage_po_date",
            "oe_procurement_po_retainage_release",
            ["po_id", "release_date"],
        )
        op.create_index(
            "ix_oe_procurement_po_retainage_release_po_id",
            "oe_procurement_po_retainage_release",
            ["po_id"],
        )

    # ------------------------------------------------------------ #5 resources
    rr = _cols(insp, "oe_resources_resource")
    if rr and "capacity_percent" not in rr:
        op.add_column(
            "oe_resources_resource",
            sa.Column("capacity_percent", sa.Integer(), nullable=True),
        )

    # ----------------------------------------------------------------- #24 risk
    rk = _cols(insp, "oe_risk_register")
    if rk:
        if "escalated" not in rk:
            op.add_column(
                "oe_risk_register",
                sa.Column(
                    "escalated",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            )
            if "ix_oe_risk_register_escalated" not in _idx(insp, "oe_risk_register"):
                op.create_index("ix_oe_risk_register_escalated", "oe_risk_register", ["escalated"])
        if "escalated_at" not in rk:
            op.add_column(
                "oe_risk_register",
                sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
            )
        if "escalation_trigger" not in rk:
            op.add_column(
                "oe_risk_register",
                sa.Column("escalation_trigger", sa.String(length=20), nullable=True),
            )
        if "escalation_threshold" not in rk:
            op.add_column(
                "oe_risk_register",
                sa.Column("escalation_threshold", sa.Integer(), nullable=True),
            )

    # ------------------------------------------------- #20 subcontractor rating
    if "oe_subcontractors_rating" not in tables:
        op.create_table(
            "oe_subcontractors_rating",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("subcontractor_id", sa.String(length=36), nullable=False),
            sa.Column("period", sa.String(length=7), nullable=False),
            sa.Column("quality_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("hse_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("schedule_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("cost_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("overall_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("basis", sa.JSON(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(
                ["subcontractor_id"],
                ["oe_subcontractors_subcontractor.id"],
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint("subcontractor_id", "period", name="uq_subcontractors_rating_period"),
        )
        op.create_index(
            "ix_oe_subcontractors_rating_subcontractor_id",
            "oe_subcontractors_rating",
            ["subcontractor_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    def drop_col(table: str, col: str) -> None:
        if col in _cols(insp, table):
            op.drop_column(table, col)

    def drop_idx(table: str, name: str) -> None:
        if name in _idx(insp, table):
            op.drop_index(name, table_name=table)

    if "oe_subcontractors_rating" in tables:
        op.drop_table("oe_subcontractors_rating")

    drop_col("oe_risk_register", "escalation_threshold")
    drop_col("oe_risk_register", "escalation_trigger")
    drop_col("oe_risk_register", "escalated_at")
    drop_idx("oe_risk_register", "ix_oe_risk_register_escalated")
    drop_col("oe_risk_register", "escalated")

    drop_col("oe_resources_resource", "capacity_percent")

    if "oe_procurement_po_retainage_release" in tables:
        op.drop_table("oe_procurement_po_retainage_release")
    drop_idx("oe_procurement_po", "ix_po_retention_percent")
    drop_col("oe_procurement_po", "retainage_released_amount")
    drop_col("oe_procurement_po", "retain_on_receipt")
    drop_col("oe_procurement_po", "retention_percent")

    drop_col("oe_finance_payment", "withholding_release_date")
    drop_idx("oe_finance_payment", "ix_finance_payment_source_claim")
    drop_col("oe_finance_payment", "source_claim_id")
    drop_col("oe_finance_payment", "withholding_amount")
    drop_idx("oe_finance_invoice", "ix_invoice_source_claim")
    drop_col("oe_finance_invoice", "source_claim_id")

    drop_idx("oe_costmodel_budget_line", "ix_costmodel_budget_line_overrun_alert")
    drop_col("oe_costmodel_budget_line", "overrun_alerted_at")
    drop_col("oe_costmodel_budget_line", "overrun_alert_threshold_pct")

    drop_col("oe_equipment_rental", "billing_calculated_at")

    drop_idx("oe_finance_invoice_item", "ix_finance_invoice_item_cost_line_id")
    drop_col("oe_finance_invoice_item", "cost_line_id")
