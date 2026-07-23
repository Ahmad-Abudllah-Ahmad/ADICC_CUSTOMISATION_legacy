# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""TOP-30 #2: field time + payroll - batch lifecycle (FSM) columns.

The v6.8 foundations (v3156) shipped ``oe_payroll_batch`` / ``oe_payroll_entry``
with a two-state ``draft -> approved`` flow. This migration widens the batch to
the full ``draft -> submitted -> approved -> posted`` lifecycle by adding the
audit timestamps and actor columns each transition records, plus the GL
transaction reference written when a batch is posted to the finance ledger.

No new tables and no field-report / cost-model schema deltas: the labour-to-cost
pipeline already lands on an auto-maintained ``category="labor"`` budget line
(no ``labour_cost_actual`` column needed) and the workforce log carries its
resource link in metadata (no ``resource_id`` / ``payroll_batch_id`` column
needed), so the only delta is the batch FSM bookkeeping below.

The embedded-PostgreSQL runtime materialises these via ``create_all`` at
startup; this migration covers external-PostgreSQL deployments that manage
schema with Alembic. Every change is inspector-guarded so a re-run (or a DB the
runtime already auto-created) is a no-op. GUID columns are VARCHAR(36) (the
app.database.GUID TypeDecorator impl).

Revision ID: v3160_field_time_payroll
Revises: v3159_wave6_jobcost_leftover
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3160_field_time_payroll"
down_revision = "v3159_wave6_jobcost_leftover"
branch_labels = None
depends_on = None

_BATCH_TABLE = "oe_payroll_batch"


def _cols(insp: sa.Inspector, table: str) -> set[str]:
    try:
        return {c["name"] for c in insp.get_columns(table)}
    except Exception:  # noqa: BLE001 - table absent
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = _cols(insp, _BATCH_TABLE)
    if not cols:
        # Table not present at all (fresh DB before create_all) - nothing to do;
        # the model carries these columns so create_all builds them.
        return

    if "submitted_at" not in cols:
        op.add_column(
            _BATCH_TABLE,
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "submitted_by" not in cols:
        op.add_column(
            _BATCH_TABLE,
            sa.Column("submitted_by", sa.String(length=36), nullable=True),
        )
    if "approved_at" not in cols:
        op.add_column(
            _BATCH_TABLE,
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "approved_by" not in cols:
        op.add_column(
            _BATCH_TABLE,
            sa.Column("approved_by", sa.String(length=36), nullable=True),
        )
    if "posted_at" not in cols:
        op.add_column(
            _BATCH_TABLE,
            sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "posted_by" not in cols:
        op.add_column(
            _BATCH_TABLE,
            sa.Column("posted_by", sa.String(length=36), nullable=True),
        )
    if "gl_transaction_ref" not in cols:
        op.add_column(
            _BATCH_TABLE,
            sa.Column("gl_transaction_ref", sa.String(length=100), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = _cols(insp, _BATCH_TABLE)
    for col in (
        "gl_transaction_ref",
        "posted_by",
        "posted_at",
        "approved_by",
        "approved_at",
        "submitted_by",
        "submitted_at",
    ):
        if col in cols:
            op.drop_column(_BATCH_TABLE, col)
