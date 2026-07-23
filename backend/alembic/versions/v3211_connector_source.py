# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""connectors: inbound document source table.

Additive only. Creates ``oe_connectors_source`` - one row per registered inbound
document source (today a watched folder) bound to a project. The last sync
outcome is kept on the row. Every operation is guarded so the migration is a
safe no-op on a fresh install that already built the table via
``Base.metadata.create_all``. The downgrade drops the table.

Revision ID: v3211_connector_source
Revises: v3210_phone_log
Create Date: 2026-06-25
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3211_connector_source"
down_revision: Union[str, Sequence[str], None] = "v3210_phone_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_TABLE = "oe_connectors_source"
_IX_PROJECT = "ix_connectors_source_project_id"
_IX_KIND = "ix_connectors_source_kind"


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
            sa.Column("kind", sa.String(length=40), nullable=False, server_default="watched_folder"),
            sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("root_path", sa.String(length=1000), nullable=False, server_default=""),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("last_synced_at", sa.String(length=40), nullable=True),
            sa.Column("last_result", sa.JSON(), nullable=True),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        )

    if _table_exists(bind, _TABLE) and not _index_exists(bind, _TABLE, _IX_PROJECT):
        op.create_index(_IX_PROJECT, _TABLE, ["project_id"])
    if _table_exists(bind, _TABLE) and not _index_exists(bind, _TABLE, _IX_KIND):
        op.create_index(_IX_KIND, _TABLE, ["kind"])

    logger.info("v3211 connector source: schema ensured")


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, _TABLE):
        for ix in (_IX_KIND, _IX_PROJECT):
            if _index_exists(bind, _TABLE, ix):
                op.drop_index(ix, table_name=_TABLE)
        op.drop_table(_TABLE)
    logger.info("v3211 connector source: reverted")
