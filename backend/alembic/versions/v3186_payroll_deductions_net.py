# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Payroll deductions and net pay.

The payroll module computed only GROSS pay (hours x rate). This migration adds
the schema for configurable withholding lines and the resulting net pay:

    oe_payroll_deduction    - one withholding line on a payslip (entry):
                              a labelled tax / social / pension / other amount,
                              either a fixed sum or a percentage of a base. The
                              platform ships NO tax tables - these are
                              user/admin-entered, configurable line items.
    oe_payroll_entry.net_amount       - String(50) Decimal-as-string.
                              net = gross - sum(deductions). Backfilled to the
                              existing ``amount`` so legacy payslips read
                              net == gross.
    oe_payroll_batch.total_deductions - String(50), backfilled "0".
    oe_payroll_batch.total_net        - String(50), backfilled to ``total_amount``
                              so legacy batches read net == gross.

Gross (``total_amount`` / entry ``amount``) is unchanged: gross labour cost is
the employer's cost and is what posts to the cost spine / GL; deductions are
employee withholdings surfaced on the payslip, not a reduction of labour cost.

The embedded-PostgreSQL runtime materialises the table and columns via
``create_all`` at startup, so this migration is for external-PostgreSQL
deployments that manage schema with Alembic. Every step is inspector-guarded so
a re-run (or a DB the runtime already auto-created) is a no-op. Additive and
backfill-safe: the net columns are populated from the existing gross in the same
upgrade, so no separate dedupe/recompute pass is required. GUID columns are
VARCHAR(36) (the app.database.GUID TypeDecorator impl). PostgreSQL-only, no
SQLite shims.

Revision ID: v3186_payroll_deductions_net
Revises: v3185_pointcloud_scan_metadata
Create Date: 2026-06-14

NOTE: this migration was authored off ``v3183_finance_ledger_idempotency`` while
that was the single head, but parallel feature streams branched
``v3184_takeoff_area_deduction`` -> ``v3185_pointcloud_scan_metadata`` off the
same parent. To keep one linear head (so ``alembic upgrade head`` never hits a
branch point), ``down_revision`` is re-pointed to ``v3185_pointcloud_scan_metadata``.
The payroll schema here is independent of the takeoff and pointcloud changes, so
the ordering is purely chain housekeeping, and none of these migrations had been
released yet.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3186_payroll_deductions_net"
down_revision = "v3185_pointcloud_scan_metadata"
branch_labels = None
depends_on = None

_BATCH_TABLE = "oe_payroll_batch"
_ENTRY_TABLE = "oe_payroll_entry"
_DEDUCTION_TABLE = "oe_payroll_deduction"


def _has_table(name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def _cols(table: str) -> set[str]:
    if not _has_table(table):
        return set()
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    # 1) Net pay column on the payslip (entry), backfilled to gross. -----------
    entry_cols = _cols(_ENTRY_TABLE)
    if entry_cols and "net_amount" not in entry_cols:
        op.add_column(
            _ENTRY_TABLE,
            sa.Column("net_amount", sa.String(length=50), nullable=False, server_default="0"),
        )
        # Backfill net = gross for existing payslips (no deductions yet).
        op.execute(
            sa.text(
                f"UPDATE {_ENTRY_TABLE} "  # noqa: S608 - fixed identifier, no user input
                "SET net_amount = amount "
                "WHERE net_amount IS NULL OR net_amount = '0' OR net_amount = ''"
            )
        )

    # 2) Deduction/net rollups on the batch, backfilled. -----------------------
    batch_cols = _cols(_BATCH_TABLE)
    if batch_cols and "total_deductions" not in batch_cols:
        op.add_column(
            _BATCH_TABLE,
            sa.Column("total_deductions", sa.String(length=50), nullable=False, server_default="0"),
        )
    if batch_cols and "total_net" not in batch_cols:
        op.add_column(
            _BATCH_TABLE,
            sa.Column("total_net", sa.String(length=50), nullable=False, server_default="0"),
        )
        # Backfill net = gross for existing batches (no deductions yet).
        op.execute(
            sa.text(
                f"UPDATE {_BATCH_TABLE} "  # noqa: S608 - fixed identifier, no user input
                "SET total_net = total_amount "
                "WHERE total_net IS NULL OR total_net = '0' OR total_net = ''"
            )
        )

    # 3) The deduction line table. --------------------------------------------
    if not _has_table(_DEDUCTION_TABLE):
        op.create_table(
            _DEDUCTION_TABLE,
            # GUID columns are stored as VARCHAR(36) (see app.database.GUID).
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("entry_id", sa.String(length=36), nullable=False),
            sa.Column("label", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("deduction_type", sa.String(length=20), nullable=False, server_default="other"),
            sa.Column("mode", sa.String(length=12), nullable=False, server_default="fixed"),
            sa.Column("value", sa.String(length=50), nullable=False, server_default="0"),
            sa.Column("base_amount", sa.String(length=50), nullable=False, server_default="0"),
            sa.Column("amount", sa.String(length=50), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default=""),
            sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(
                ["entry_id"],
                [f"{_ENTRY_TABLE}.id"],
                ondelete="CASCADE",
            ),
        )
        op.create_index(op.f("ix_oe_payroll_deduction_entry_id"), _DEDUCTION_TABLE, ["entry_id"])
        op.create_index("ix_oe_payroll_deduction_entry_ordinal", _DEDUCTION_TABLE, ["entry_id", "ordinal"])


def downgrade() -> None:
    if _has_table(_DEDUCTION_TABLE):
        op.drop_table(_DEDUCTION_TABLE)
    batch_cols = _cols(_BATCH_TABLE)
    if "total_net" in batch_cols:
        op.drop_column(_BATCH_TABLE, "total_net")
    if "total_deductions" in batch_cols:
        op.drop_column(_BATCH_TABLE, "total_deductions")
    if "net_amount" in _cols(_ENTRY_TABLE):
        op.drop_column(_ENTRY_TABLE, "net_amount")
