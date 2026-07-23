# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""TOP-30 #20: one rating row per subcontractor per period.

Adds the unique constraint ``uq_subcontractors_rating_period`` on
``oe_subcontractors_rating(subcontractor_id, period)``. This is the
database backstop that makes the monthly-rollup compute idempotent: a
double-compute of the same month (a cron re-run, or a manual trigger
landing twice) can never insert a duplicate rating row.

Fresh installs get this constraint from the model ``__table_args__`` via
``Base.metadata.create_all``. The embedded-PostgreSQL runtime auto-migrator
only adds missing columns, not constraints, so this migration covers
external-PostgreSQL deployments that manage schema with Alembic.

The constraint is only created when the table holds no pre-existing
duplicate ``(subcontractor_id, period)`` rows (older builds had only a
non-unique index, so a stray duplicate is theoretically possible). When a
duplicate is found the migration logs and skips rather than failing the
whole upgrade; the service-layer upsert still keeps new rows unique.

Revision ID: v3158_subcontractor_scorecards
Revises: v3157_wave5_top30
Create Date: 2026-06-04
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

# Alembic identifiers
revision = "v3158_subcontractor_scorecards"
down_revision = "v3157_wave5_top30"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_TABLE = "oe_subcontractors_rating"
_CONSTRAINT = "uq_subcontractors_rating_period"
_COLUMNS = ("subcontractor_id", "period")


def _constraint_exists(inspector: sa.engine.reflection.Inspector) -> bool:
    names = {uc["name"] for uc in inspector.get_unique_constraints(_TABLE)}
    # Some builds may have materialised it as a unique index instead.
    names |= {ix["name"] for ix in inspector.get_indexes(_TABLE) if ix.get("unique")}
    return _CONSTRAINT in names


def upgrade() -> None:
    """Add the (subcontractor_id, period) unique constraint, if safe."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    if _constraint_exists(inspector):
        return

    # Guard: only create the constraint when the data is already unique.
    dup = bind.execute(
        sa.text(
            f"""
            SELECT subcontractor_id, period
            FROM {_TABLE}
            GROUP BY subcontractor_id, period
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if dup is not None:
        logger.warning(
            "v3158: %s holds duplicate (subcontractor_id, period) rows; "
            "skipping unique constraint. De-duplicate then re-run.",
            _TABLE,
        )
        return

    op.create_unique_constraint(_CONSTRAINT, _TABLE, list(_COLUMNS))


def downgrade() -> None:
    """Drop the (subcontractor_id, period) unique constraint."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    if not _constraint_exists(inspector):
        return
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="unique")
