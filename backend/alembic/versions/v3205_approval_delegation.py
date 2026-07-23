# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""approval_routes: out-of-office delegation + per-instance assignee override.

Additive only. Two changes that together let an approval keep moving when the
named approver is away:

1. ``oe_approval_routes_delegation`` - an out-of-office hand-off of one user's
   approvals to a stand-in, optionally scoped to a project and a time window.
2. ``oe_approval_routes_instance.current_assignee_user_id`` - a nullable
   override pinning who must act on the instance's current step (the "ball in
   court" for that approval), set by a one-tap reassignment without editing the
   shared route template.

Every operation is guarded so the migration is a safe no-op on a fresh install
that already built the schema via ``Base.metadata.create_all``. The downgrade
drops the column and the table.

Revision ID: v3205_approval_delegation
Revises: v3204_ai_agents_trust
Create Date: 2026-06-24
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3205_approval_delegation"
down_revision: Union[str, Sequence[str], None] = "v3204_ai_agents_trust"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_INSTANCE_TABLE = "oe_approval_routes_instance"
_ASSIGNEE_COLUMN = "current_assignee_user_id"
_DELEGATION_TABLE = "oe_approval_routes_delegation"
_IX_DELEGATOR = "ix_approval_delegation_delegator_active"
_IX_DELEGATE = "ix_approval_delegation_delegate_active"


def _table_exists(bind: sa.engine.Connection, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def _column_exists(bind: sa.engine.Connection, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def _index_exists(bind: sa.engine.Connection, table: str, index: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(ix["name"] == index for ix in insp.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Per-instance assignee override.
    if _table_exists(bind, _INSTANCE_TABLE) and not _column_exists(bind, _INSTANCE_TABLE, _ASSIGNEE_COLUMN):
        op.add_column(
            _INSTANCE_TABLE,
            sa.Column(
                _ASSIGNEE_COLUMN,
                sa.String(length=36),
                sa.ForeignKey("oe_users_user.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        logger.info("v3205 approval delegation: assignee override column added")

    # 2. Delegation table.
    if not _table_exists(bind, _DELEGATION_TABLE):
        op.create_table(
            _DELEGATION_TABLE,
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column(
                "delegator_user_id",
                sa.String(length=36),
                sa.ForeignKey("oe_users_user.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "delegate_user_id",
                sa.String(length=36),
                sa.ForeignKey("oe_users_user.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column(
                "created_by",
                sa.String(length=36),
                sa.ForeignKey("oe_users_user.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    if _table_exists(bind, _DELEGATION_TABLE) and not _index_exists(bind, _DELEGATION_TABLE, _IX_DELEGATOR):
        op.create_index(_IX_DELEGATOR, _DELEGATION_TABLE, ["delegator_user_id", "is_active"])
    if _table_exists(bind, _DELEGATION_TABLE) and not _index_exists(bind, _DELEGATION_TABLE, _IX_DELEGATE):
        op.create_index(_IX_DELEGATE, _DELEGATION_TABLE, ["delegate_user_id", "is_active"])

    logger.info("v3205 approval delegation: schema ensured")


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, _DELEGATION_TABLE):
        if _index_exists(bind, _DELEGATION_TABLE, _IX_DELEGATE):
            op.drop_index(_IX_DELEGATE, table_name=_DELEGATION_TABLE)
        if _index_exists(bind, _DELEGATION_TABLE, _IX_DELEGATOR):
            op.drop_index(_IX_DELEGATOR, table_name=_DELEGATION_TABLE)
        op.drop_table(_DELEGATION_TABLE)

    if _column_exists(bind, _INSTANCE_TABLE, _ASSIGNEE_COLUMN):
        op.drop_column(_INSTANCE_TABLE, _ASSIGNEE_COLUMN)

    logger.info("v3205 approval delegation: reverted")
