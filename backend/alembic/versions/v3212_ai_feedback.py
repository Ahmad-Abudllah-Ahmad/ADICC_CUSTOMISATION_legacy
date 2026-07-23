# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""ai_agents: generic AI feedback sink.

Additive only. Creates ``oe_ai_feedback`` - one row per correct / incorrect
verdict a user records on any AI output in the app. The accuracy scoreboard
already scores agent *runs*, but most AI the user sees (the AI Estimator
result, the match-elements suggestions, the cost advisor's answers) has no run
row to attach a verdict to. This is the generic sink for that trust loop:
``surface`` names where the verdict came from, ``ref`` is an optional opaque
pointer to the specific output, ``correct`` is the thumbs up / down, and
``note`` is an optional free-text correction. Money-free; scoped to the caller
and optionally one of their projects.

Every operation is guarded so the migration is a safe no-op on a fresh install
that already built the table via ``Base.metadata.create_all``. The downgrade
drops the table.

Revision ID: v3212_ai_feedback
Revises: v3211_connector_source
Create Date: 2026-06-26
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3212_ai_feedback"
down_revision: Union[str, Sequence[str], None] = "v3211_connector_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_TABLE = "oe_ai_feedback"
_IX_USER = "ix_ai_feedback_user_id"
_IX_PROJECT = "ix_ai_feedback_project_id"
_IX_SURFACE = "ix_ai_feedback_surface"


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
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("project_id", sa.String(length=36), nullable=True),
            sa.Column("surface", sa.String(length=40), nullable=False),
            sa.Column("ref", sa.String(length=200), nullable=True),
            sa.Column("correct", sa.Boolean(), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
        )

    if _table_exists(bind, _TABLE) and not _index_exists(bind, _TABLE, _IX_USER):
        op.create_index(_IX_USER, _TABLE, ["user_id"])
    if _table_exists(bind, _TABLE) and not _index_exists(bind, _TABLE, _IX_PROJECT):
        op.create_index(_IX_PROJECT, _TABLE, ["project_id"])
    if _table_exists(bind, _TABLE) and not _index_exists(bind, _TABLE, _IX_SURFACE):
        op.create_index(_IX_SURFACE, _TABLE, ["surface"])

    logger.info("v3212 ai feedback: schema ensured")


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, _TABLE):
        for ix in (_IX_SURFACE, _IX_PROJECT, _IX_USER):
            if _index_exists(bind, _TABLE, ix):
                op.drop_index(ix, table_name=_TABLE)
        op.drop_table(_TABLE)
    logger.info("v3212 ai feedback: reverted")
