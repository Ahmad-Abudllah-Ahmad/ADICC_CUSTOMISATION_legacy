# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""TOP-30 #2: field labour to job cost - payroll batches.

Adds two tables:

* ``oe_payroll_batch`` - one draft/approved pay run per (project, period),
  with denormalised hour/amount totals for the list view.
* ``oe_payroll_entry`` - one line per (worker, date): hours x rate = amount,
  always in the project base currency (the generator converts before insert).

The embedded-PostgreSQL runtime creates these via ``create_all`` at startup;
this migration covers external-PostgreSQL deployments that manage schema with
Alembic. Idempotent: it inspects existing tables first so a re-run (or a DB
the runtime already auto-created) is a no-op.

Revision ID: v3156_payroll_batches
Revises: v3155_finance_connectors
Create Date: 2026-06-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Alembic identifiers
revision = "v3156_payroll_batches"
down_revision = "v3155_finance_connectors"
branch_labels = None
depends_on = None

_BATCH_TABLE = "oe_payroll_batch"
_ENTRY_TABLE = "oe_payroll_entry"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if _BATCH_TABLE not in existing:
        op.create_table(
            _BATCH_TABLE,
            # GUID columns are stored as VARCHAR(36) (see app.database.GUID).
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("project_id", sa.String(length=36), nullable=False),
            sa.Column("period_label", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("period_start", sa.String(length=20), nullable=True),
            sa.Column("period_end", sa.String(length=20), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default=""),
            sa.Column("total_hours", sa.String(length=50), nullable=False, server_default="0"),
            sa.Column("total_amount", sa.String(length=50), nullable=False, server_default="0"),
            sa.Column("entry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(
                ["project_id"],
                ["oe_projects_project.id"],
                ondelete="CASCADE",
            ),
        )
        op.create_index(op.f("ix_oe_payroll_batch_project_id"), _BATCH_TABLE, ["project_id"])
        op.create_index(op.f("ix_oe_payroll_batch_status"), _BATCH_TABLE, ["status"])
        op.create_index("ix_oe_payroll_batch_project_status", _BATCH_TABLE, ["project_id", "status"])

    if _ENTRY_TABLE not in existing:
        op.create_table(
            _ENTRY_TABLE,
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("batch_id", sa.String(length=36), nullable=False),
            sa.Column("resource_id", sa.String(length=36), nullable=True),
            sa.Column("worker", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("work_date", sa.String(length=20), nullable=True),
            sa.Column("hours", sa.String(length=50), nullable=False, server_default="0"),
            sa.Column("rate", sa.String(length=50), nullable=False, server_default="0"),
            sa.Column("amount", sa.String(length=50), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default=""),
            sa.Column("source", sa.String(length=40), nullable=False, server_default="fieldreport"),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(
                ["batch_id"],
                [f"{_BATCH_TABLE}.id"],
                ondelete="CASCADE",
            ),
        )
        op.create_index(op.f("ix_oe_payroll_entry_batch_id"), _ENTRY_TABLE, ["batch_id"])
        op.create_index(op.f("ix_oe_payroll_entry_resource_id"), _ENTRY_TABLE, ["resource_id"])
        op.create_index("ix_oe_payroll_entry_batch_date", _ENTRY_TABLE, ["batch_id", "work_date"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    if _ENTRY_TABLE in existing:
        op.drop_table(_ENTRY_TABLE)
    if _BATCH_TABLE in existing:
        op.drop_table(_BATCH_TABLE)
