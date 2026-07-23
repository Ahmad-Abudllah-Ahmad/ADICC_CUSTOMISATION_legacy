# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""event reconciliation: record-link table.

Additive only. Creates ``oe_record_link`` - one row per reviewed correlation
between two heterogeneous records (a change order, a piece of correspondence, a
variation, a management-of-change entry, ...) that the pure reconciliation
engine judged to describe the same underlying event. The engine recomputes the
suggestions on every read; a row exists here only once a reviewer has confirmed
or rejected a suggested link, so the table is the durable record of human
decisions, not a cache of suggestions. Each endpoint is an opaque ``(type, id)``
pair so a new source type never needs a schema change.

Every operation is guarded so the migration is a safe no-op on a fresh install
that already built the table via ``Base.metadata.create_all``. The downgrade
drops the table.

Revision ID: v3209_record_link
Revises: v3208_cost_recovery_apportionment
Create Date: 2026-06-25
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3209_record_link"
down_revision: Union[str, Sequence[str], None] = "v3208_cost_recovery_apportionment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_TABLE = "oe_record_link"
_IX_PROJECT = "ix_record_link_project_id"
_IX_STATUS = "ix_record_link_status"


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
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("left_type", sa.String(length=60), nullable=False, server_default=""),
            sa.Column("left_id", sa.String(length=36), nullable=False, server_default=""),
            sa.Column("right_type", sa.String(length=60), nullable=False, server_default=""),
            sa.Column("right_id", sa.String(length=36), nullable=False, server_default=""),
            sa.Column("relation", sa.String(length=40), nullable=False, server_default="same_event"),
            sa.Column("confidence", sa.Numeric(6, 4), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="suggested"),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        )

    if _table_exists(bind, _TABLE) and not _index_exists(bind, _TABLE, _IX_PROJECT):
        op.create_index(_IX_PROJECT, _TABLE, ["project_id"])
    if _table_exists(bind, _TABLE) and not _index_exists(bind, _TABLE, _IX_STATUS):
        op.create_index(_IX_STATUS, _TABLE, ["status"])

    logger.info("v3209 record link: schema ensured")


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, _TABLE):
        if _index_exists(bind, _TABLE, _IX_STATUS):
            op.drop_index(_IX_STATUS, table_name=_TABLE)
        if _index_exists(bind, _TABLE, _IX_PROJECT):
            op.drop_index(_IX_PROJECT, table_name=_TABLE)
        op.drop_table(_TABLE)
    logger.info("v3209 record link: reverted")
