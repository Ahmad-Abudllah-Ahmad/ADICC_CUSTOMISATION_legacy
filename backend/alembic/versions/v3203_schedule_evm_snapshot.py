# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""schedule: persisted EVM snapshots for performance trends.

Additive only. Adds the ``oe_schedule_evm_snapshot`` table that freezes a
schedule's time-phased earned-value rollup (planned value, earned value, budget
at completion and the EV/PV schedule performance index) at a data date, so the
cost / schedule performance trend can be charted over time. Snapshots accrue
automatically as the schedule's data date advances.

A unique constraint on ``(schedule_id, data_date)`` makes re-recording at the
same data date an upsert (one trend point per date), and the table cascade-
deletes with its parent schedule. Money columns are ``Numeric(20, 4)`` (Decimal),
matching ``oe_schedule_activity.cost_planned``. There is intentionally no actual
cost (AC) or cost performance index (CPI) column - the schedule EVM rollup never
computes an actual cost.

Every operation is guarded so the migration is a safe no-op on a fresh install
that already built the schema via ``Base.metadata.create_all``. The downgrade
drops the table.

Revision ID: v3203_schedule_evm_snapshot
Revises: v3202_schedule_realtime_revision
Create Date: 2026-06-23
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3203_schedule_evm_snapshot"
down_revision: Union[str, Sequence[str], None] = "v3202_schedule_realtime_revision"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_TABLE = "oe_schedule_evm_snapshot"
_INDEX = "ix_sched_evm_snapshot_schedule_date"
_UNIQUE = "uq_sched_evm_snapshot_sched_date"


def _table_exists(bind: sa.engine.Connection, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def _index_exists(bind: sa.engine.Connection, table: str, index: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(ix["name"] == index for ix in insp.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column(
                "schedule_id",
                sa.String(length=36),
                sa.ForeignKey("oe_schedule_schedule.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("project_id", sa.String(length=36), nullable=False),
            sa.Column("data_date", sa.String(length=40), nullable=False),
            sa.Column("pv", sa.Numeric(20, 4), nullable=False, server_default="0"),
            sa.Column("ev", sa.Numeric(20, 4), nullable=False, server_default="0"),
            sa.Column("bac", sa.Numeric(20, 4), nullable=False, server_default="0"),
            sa.Column("spi", sa.Numeric(10, 3), nullable=True),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("schedule_id", "data_date", name=_UNIQUE),
        )

    if _table_exists(bind, _TABLE) and not _index_exists(bind, _TABLE, _INDEX):
        op.create_index(_INDEX, _TABLE, ["schedule_id", "data_date"])

    logger.info("v3203 schedule EVM snapshot: table ensured")


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, _TABLE):
        if _index_exists(bind, _TABLE, _INDEX):
            op.drop_index(_INDEX, table_name=_TABLE)
        op.drop_table(_TABLE)

    logger.info("v3203 schedule EVM snapshot: reverted")
