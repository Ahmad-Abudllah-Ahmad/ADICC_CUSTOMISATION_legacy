# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""portfolio T3.3: cross-schedule dependency links for portfolio CPM.

Adds ``oe_portfolio_cross_link`` - a dependency between two activities living in
different schedules. The portfolio (schedule-of-schedules) CPM treats a link
whose both endpoints are in scope as a real cross-project edge. All four
references are plain GUIDs (no cross-module FK to the ``schedule`` module's
tables, matching the codebase precedent and the sibling portfolio tables).

Guarded so re-applying where ``create_all`` already built the schema is a no-op;
the downgrade fully reverses the upgrade.

Revision ID: v3201_portfolio_cross_link
Revises: v3200_resource_depth
Create Date: 2026-06-23
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3201_portfolio_cross_link"
down_revision: Union[str, Sequence[str], None] = "v3200_resource_depth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_TABLE = "oe_portfolio_cross_link"

_INDEXES: tuple[tuple[str, list[str]], ...] = (
    ("ix_portfolio_cross_link_predecessor", ["predecessor_schedule_id"]),
    ("ix_portfolio_cross_link_successor", ["successor_schedule_id"]),
)


def _table_exists(bind: sa.engine.Connection, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def _index_exists(bind: sa.engine.Connection, table: str, index: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(ix["name"] == index for ix in insp.get_indexes(table))


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column("predecessor_schedule_id", sa.String(length=36), nullable=False),
            sa.Column("predecessor_activity_id", sa.String(length=36), nullable=False),
            sa.Column("successor_schedule_id", sa.String(length=36), nullable=False),
            sa.Column("successor_activity_id", sa.String(length=36), nullable=False),
            sa.Column("dep_type", sa.String(length=2), nullable=False, server_default="FS"),
            sa.Column("lag_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        )

    for index_name, columns in _INDEXES:
        if _table_exists(bind, _TABLE) and not _index_exists(bind, _TABLE, index_name):
            op.create_index(index_name, _TABLE, columns)

    logger.info("v3201 portfolio cross-link: table + indexes ensured")


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, _TABLE):
        for index_name, _columns in _INDEXES:
            if _index_exists(bind, _TABLE, index_name):
                op.drop_index(index_name, table_name=_TABLE)
        op.drop_table(_TABLE)

    logger.info("v3201 portfolio cross-link: reverted")
