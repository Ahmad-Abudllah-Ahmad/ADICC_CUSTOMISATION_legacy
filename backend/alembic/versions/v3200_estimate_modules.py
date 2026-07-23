# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Estimating-wave schema: price_as_of on cost items, and a single head.

Two jobs in one revision.

1. Collapse the four alembic heads that had accumulated from parallel work
   (``v3135_project_unit_system``, ``v3160_field_time_payroll``,
   ``v3165_agent_automation``, ``v3187_costs_mass_pricing``) back into one, so
   external-PostgreSQL deployments have an unambiguous ``alembic stamp head``
   and the migration history stays linear from here on.

2. Add the one column the estimating wave needs on an EXISTING table that
   ``create_all`` cannot alter: ``oe_costs_item.price_as_of`` (a nullable
   date). It records when a stored rate was last known good, so the certainty
   badge can flag a rate that is stale by price date, not just by usage.

Every other table the estimating wave introduces (price index, labor rates,
resource-summary snapshots, preliminaries, allowances, waste factors,
production norms, conceptual estimates, estimate basis) is a brand-new table
that ``Base.metadata.create_all`` builds on a fresh install and the embedded
runtime auto-heals, so none of them needs a hand-written step here.

The column step is inspector-guarded, so this is a no-op on a database the
runtime already auto-created and is safe to re-run. Additive and
backfill-safe. PostgreSQL-only, no SQLite shims.

Revision ID: v3200_estimate_modules
Revises: v3135_project_unit_system, v3160_field_time_payroll, v3165_agent_automation, v3187_costs_mass_pricing
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3200_estimate_modules"
down_revision = (
    "v3135_project_unit_system",
    "v3160_field_time_payroll",
    "v3165_agent_automation",
    "v3187_costs_mass_pricing",
)
branch_labels = None
depends_on = None

_TABLE = "oe_costs_item"
_COLUMN = "price_as_of"


def _has_table(name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    insp = sa.inspect(op.get_bind())
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _has_table(_TABLE):
        return
    if not _has_column(_TABLE, _COLUMN):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Date(), nullable=True))


def downgrade() -> None:
    if _has_column(_TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
