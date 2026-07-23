# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""schedule T3.4: per-activity optimistic-concurrency revision.

Additive only. Adds ``oe_schedule_activity.revision`` - a monotonic integer
bumped on every guarded write so a stale concurrent edit is rejected rather
than silently overwriting a newer one. Existing rows backfill to ``0`` (the
same value a freshly created activity carries), so behaviour is unchanged until
the guarded-write path is exercised. The operation is guarded so the migration
is a safe no-op on a fresh install that already built the schema via
``Base.metadata.create_all``. The downgrade drops the column.

Revision ID: v3202_schedule_realtime_revision
Revises: v3201_portfolio_cross_link
Create Date: 2026-06-23
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3202_schedule_realtime_revision"
down_revision: Union[str, Sequence[str], None] = "v3201_portfolio_cross_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_ACTIVITY = "oe_schedule_activity"
_COLUMN = "revision"


def _table_exists(bind: sa.engine.Connection, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def _column_exists(bind: sa.engine.Connection, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, _ACTIVITY) and not _column_exists(bind, _ACTIVITY, _COLUMN):
        op.add_column(
            _ACTIVITY,
            sa.Column(_COLUMN, sa.Integer(), nullable=False, server_default="0"),
        )
    logger.info("v3202 schedule realtime: activity.revision ensured")


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, _ACTIVITY) and _column_exists(bind, _ACTIVITY, _COLUMN):
        op.drop_column(_ACTIVITY, _COLUMN)
    logger.info("v3202 schedule realtime: reverted")
