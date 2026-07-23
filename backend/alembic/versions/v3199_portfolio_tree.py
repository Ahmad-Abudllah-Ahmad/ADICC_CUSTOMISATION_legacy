# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""portfolio T3.3: portfolio / programme tree.

Adds the enterprise schedule-of-schedules navigation overlay:

* ``oe_portfolio_node`` - adjacency-list tree of portfolio / programme /
  sub-programme nodes (self-FK parent SET NULL).
* ``oe_portfolio_membership`` - thin link filing a project under exactly one
  node (unique on ``project_id``); ``project_id`` is a plain GUID (no
  cross-module FK), matching the codebase precedent.

The tree is a navigation / scoping overlay, not a security principal. Every
operation is guarded so the migration is a safe no-op on a fresh install that
already booted the app (``Base.metadata.create_all`` builds the current schema).
The downgrade fully reverses the upgrade.

Revision ID: v3199_portfolio_tree
Revises: v3198_schedule_progress_rigor
Create Date: 2026-06-23
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3199_portfolio_tree"
down_revision: Union[str, Sequence[str], None] = "v3198_schedule_progress_rigor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_NODE = "oe_portfolio_node"
_MEMBERSHIP = "oe_portfolio_membership"


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


_INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    (_NODE, "ix_oe_portfolio_node_parent_id", ["parent_id"]),
    (_NODE, "ix_oe_portfolio_node_owner_id", ["owner_id"]),
    (_MEMBERSHIP, "ix_oe_portfolio_membership_node_id", ["node_id"]),
)


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, _NODE):
        op.create_table(
            _NODE,
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "parent_id",
                sa.String(length=36),
                sa.ForeignKey("oe_portfolio_node.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("node_type", sa.String(length=20), nullable=False, server_default="programme"),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("code", sa.String(length=50), nullable=False, server_default=""),
            sa.Column("owner_id", sa.String(length=36), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        )

    if not _table_exists(bind, _MEMBERSHIP):
        op.create_table(
            _MEMBERSHIP,
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "node_id",
                sa.String(length=36),
                sa.ForeignKey("oe_portfolio_node.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("project_id", sa.String(length=36), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("project_id", name="uq_portfolio_membership_project"),
        )

    for table, index_name, columns in _INDEXES:
        if _table_exists(bind, table) and not _index_exists(bind, table, index_name):
            op.create_index(index_name, table, columns)

    logger.info("v3199 portfolio tree: 2 tables + indexes ensured")


def downgrade() -> None:
    bind = op.get_bind()

    # Child table before parent (FK order).
    for table in (_MEMBERSHIP, _NODE):
        if _table_exists(bind, table):
            for tbl, index_name, _columns in _INDEXES:
                if tbl == table and _index_exists(bind, table, index_name):
                    op.drop_index(index_name, table_name=table)
            op.drop_table(table)

    logger.info("v3199 portfolio tree: reverted")
