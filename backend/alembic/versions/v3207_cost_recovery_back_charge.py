# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""cost recovery: back-charge ledger table.

Additive only. Creates ``oe_cost_recovery_back_charge`` - one row per cost the
project intends to recover from the party responsible for causing it, with its
amounts (gross, chargeable share, recovered) and commercial state.

Every operation is guarded so the migration is a safe no-op on a fresh install
that already built the table via ``Base.metadata.create_all``. The downgrade
drops the table.

Revision ID: v3207_cost_recovery_back_charge
Revises: v3206_change_ball_in_court
Create Date: 2026-06-24
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3207_cost_recovery_back_charge"
down_revision: Union[str, Sequence[str], None] = "v3206_change_ball_in_court"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_TABLE = "oe_cost_recovery_back_charge"
_IX_PROJECT = "ix_cost_recovery_back_charge_project_id"
_IX_STATUS = "ix_cost_recovery_back_charge_status"


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
            sa.Column("source_ref", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("responsible_party", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("basis", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("gross_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("chargeable_pct", sa.Numeric(6, 4), nullable=False, server_default="1"),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="proposed"),
            sa.Column("recovered_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("agreed_at", sa.String(length=40), nullable=True),
            sa.Column("recovered_at", sa.String(length=40), nullable=True),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        )

    if _table_exists(bind, _TABLE) and not _index_exists(bind, _TABLE, _IX_PROJECT):
        op.create_index(_IX_PROJECT, _TABLE, ["project_id"])
    if _table_exists(bind, _TABLE) and not _index_exists(bind, _TABLE, _IX_STATUS):
        op.create_index(_IX_STATUS, _TABLE, ["status"])

    logger.info("v3207 cost recovery: schema ensured")


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, _TABLE):
        if _index_exists(bind, _TABLE, _IX_STATUS):
            op.drop_index(_IX_STATUS, table_name=_TABLE)
        if _index_exists(bind, _TABLE, _IX_PROJECT):
            op.drop_index(_IX_PROJECT, table_name=_TABLE)
        op.drop_table(_TABLE)
    logger.info("v3207 cost recovery: reverted")
