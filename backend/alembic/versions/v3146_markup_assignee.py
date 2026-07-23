# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""markups: add nullable assignee_id FK to oe_markups_markup.

Markups were anonymous "post-it notes" with no follow-up owner. Teams
need to assign individual markups to specific users so reviewers know
who is on the hook. This migration adds the column + FK + index.

Nullable on purpose: existing markups have no assignee, and many never
need one (rough sketches, observations). Unassigned remains the
default state. ``ON DELETE SET NULL`` so deleting a user does not
cascade-destroy their pending markup queue.

Idempotent: skips when the column already exists (fresh installs where
``Base.metadata.create_all`` materialised the new column from the ORM
model before alembic ran).

Revision ID: v3146_markup_assignee
Revises: v3145_demo_project_addresses
Create Date: 2026-05-28
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3146_markup_assignee"
down_revision: Union[str, None] = "v3145_demo_project_addresses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_TABLE = "oe_markups_markup"
_COLUMN = "assignee_id"
_INDEX = "ix_oe_markups_markup_assignee_id"
_FK = "fk_oe_markups_markup_assignee_id_oe_users_user"


def _table_exists(bind: sa.engine.Connection, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def _column_exists(bind: sa.engine.Connection, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def _index_exists(bind: sa.engine.Connection, table: str, index: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(i["name"] == index for i in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, _TABLE):
        logger.info("v3146: %s table absent, skipping (fresh install via create_all).", _TABLE)
        return

    if _column_exists(bind, _TABLE, _COLUMN):
        logger.info("v3146: %s.%s already present, skipping column add.", _TABLE, _COLUMN)
    else:
        # SQLite cannot add a column with an inline FK constraint via plain
        # ALTER TABLE — use batch mode so SQLite gets the table-recreate
        # treatment while PostgreSQL gets a clean ALTER. The named FK
        # constraint is created inside the batch so it survives the rebuild.
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.add_column(
                sa.Column(
                    _COLUMN,
                    sa.CHAR(length=32),  # matches GUID() storage on SQLite; PG sees UUID via the type adapter
                    nullable=True,
                )
            )
            batch_op.create_foreign_key(
                _FK,
                "oe_users_user",
                [_COLUMN],
                ["id"],
                ondelete="SET NULL",
            )

    if _index_exists(bind, _TABLE, _INDEX):
        logger.info("v3146: index %s already present, skipping.", _INDEX)
    else:
        op.create_index(_INDEX, _TABLE, [_COLUMN])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, _TABLE):
        return

    if _index_exists(bind, _TABLE, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)

    if _column_exists(bind, _TABLE, _COLUMN):
        with op.batch_alter_table(_TABLE) as batch_op:
            # batch mode drops the inline FK alongside the column on SQLite;
            # on PG the named constraint is removed via drop_constraint.
            try:
                batch_op.drop_constraint(_FK, type_="foreignkey")
            except Exception:  # noqa: BLE001 — best-effort, batch may have already removed it
                pass
            batch_op.drop_column(_COLUMN)
