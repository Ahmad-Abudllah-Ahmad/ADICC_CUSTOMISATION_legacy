# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""takeoff: opening-deduction flag for net area takeoff.

Area measurements could not represent an opening / void (a door, window or
cut-out), so a measured area was always a gross area and the rollup had no way
to compute net = gross - openings. This adds:

    oe_takeoff_measurement.is_deduction  - NOT NULL boolean, server_default 0.
        When true the area measurement is an opening and its area is
        subtracted from the gross area of its group in the net-area rollup.

The column is stored as a positive gross area on the row itself (the shoelace
recompute is sign-agnostic); only the rollup subtracts it, and the link-to-boq
push refuses a lone deduction so a void can never masquerade as a BOQ quantity.

The embedded PostgreSQL runtime materialises the column via ``create_all`` at
startup, so this migration is for external PostgreSQL deployments that manage
schema with Alembic. Every step is presence-guarded so a re-run, or a DB the
runtime already auto-created, is a no-op. Additive and backfill-safe: existing
rows take the server_default 0 (a normal, non-deduction measurement), so no
data migration is required. PostgreSQL-only, no SQLite shims.

Revision ID: v3184_takeoff_area_deduction
Revises: v3183_finance_ledger_idempotency
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3184_takeoff_area_deduction"
down_revision = "v3183_finance_ledger_idempotency"
branch_labels = None
depends_on = None

_TABLE = "oe_takeoff_measurement"
_COLUMN = "is_deduction"


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _has_column(_TABLE, _COLUMN):
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    if _has_column(_TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
