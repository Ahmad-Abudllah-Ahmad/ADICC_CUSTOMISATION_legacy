# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""value: admin-tunable hours-saved minute factors.

Additive only. Creates ``oe_value_time_factor`` - one row per tenant override of
a hours-saved ``(module, action)`` minute factor. The table is empty on a fresh
install (every pair falls back to the conservative seed default in
``app.modules.value.time_saved.DEFAULT_FACTORS``), so there is nothing to seed
and nothing to migrate. ``minutes`` is Numeric, never a money column - it carries
minutes of saved effort, not currency. Every operation is guarded so the
migration is a safe no-op when ``Base.metadata.create_all`` already built the
table on a fresh boot. The downgrade drops the table.

Revision ID: v3213_value_time_factor
Revises: v3212_ai_feedback
Create Date: 2026-06-26
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3213_value_time_factor"
down_revision: Union[str, Sequence[str], None] = "v3212_ai_feedback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_TABLE = "oe_value_time_factor"
_IX_TENANT = "ix_value_time_factor_tenant_id"
_UQ_SCOPE = "uq_value_time_factor_scope"


def _table_exists(bind: sa.engine.Connection, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def _index_exists(bind: sa.engine.Connection, table: str, index: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(ix["name"] == index for ix in insp.get_indexes(table))


def _unique_exists(bind: sa.engine.Connection, table: str, name: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(uc["name"] == name for uc in insp.get_unique_constraints(table))


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, _TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("tenant_id", sa.String(length=36), nullable=True),
            sa.Column("module", sa.String(length=80), nullable=False),
            sa.Column("action", sa.String(length=120), nullable=False),
            sa.Column("minutes", sa.Numeric(10, 2), nullable=False),
            sa.UniqueConstraint("tenant_id", "module", "action", name=_UQ_SCOPE),
        )

    if _table_exists(bind, _TABLE) and not _index_exists(bind, _TABLE, _IX_TENANT):
        op.create_index(_IX_TENANT, _TABLE, ["tenant_id"])

    logger.info("v3212 value time factor: schema ensured")


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, _TABLE):
        if _index_exists(bind, _TABLE, _IX_TENANT):
            op.drop_index(_IX_TENANT, table_name=_TABLE)
        op.drop_table(_TABLE)
    logger.info("v3212 value time factor: reverted")
