# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""phone log: verbal-instruction capture table.

Additive only. Creates ``oe_phonelog_phone_log`` - one row per captured phone
call, voice note, or verbal instruction, normalized into a dispute-ready record
(canonical direction and channel, a clean party list, a duration, a short
summary, and the instruction-bearing sentences pulled out of the transcript).
The raw transcript is kept verbatim as the underlying evidence. Audio is
optional: the column ``audio_storage_key`` is reserved for a future
transcription provider, but the transcript is the dispute-relevant artifact.

Every operation is guarded so the migration is a safe no-op on a fresh install
that already built the table via ``Base.metadata.create_all``. The downgrade
drops the table.

Revision ID: v3210_phone_log
Revises: v3209_record_link
Create Date: 2026-06-25
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3210_phone_log"
down_revision: Union[str, Sequence[str], None] = "v3209_record_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_TABLE = "oe_phonelog_phone_log"
_IX_PROJECT = "ix_phonelog_phone_log_project_id"
_IX_DIRECTION = "ix_phonelog_phone_log_direction"
_IX_CHANNEL = "ix_phonelog_phone_log_channel"
_IX_STATUS = "ix_phonelog_phone_log_status"


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
            sa.Column("direction", sa.String(length=20), nullable=False, server_default="unknown"),
            sa.Column("channel", sa.String(length=20), nullable=False, server_default="phone"),
            sa.Column("parties", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("occurred_at", sa.String(length=40), nullable=True),
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
            sa.Column("transcript", sa.Text(), nullable=False, server_default=""),
            sa.Column("summary", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("instructions", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("audio_storage_key", sa.String(length=512), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="logged"),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        )

    if _table_exists(bind, _TABLE) and not _index_exists(bind, _TABLE, _IX_PROJECT):
        op.create_index(_IX_PROJECT, _TABLE, ["project_id"])
    if _table_exists(bind, _TABLE) and not _index_exists(bind, _TABLE, _IX_DIRECTION):
        op.create_index(_IX_DIRECTION, _TABLE, ["direction"])
    if _table_exists(bind, _TABLE) and not _index_exists(bind, _TABLE, _IX_CHANNEL):
        op.create_index(_IX_CHANNEL, _TABLE, ["channel"])
    if _table_exists(bind, _TABLE) and not _index_exists(bind, _TABLE, _IX_STATUS):
        op.create_index(_IX_STATUS, _TABLE, ["status"])

    logger.info("v3210 phone log: schema ensured")


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, _TABLE):
        for ix in (_IX_STATUS, _IX_CHANNEL, _IX_DIRECTION, _IX_PROJECT):
            if _index_exists(bind, _TABLE, ix):
                op.drop_index(ix, table_name=_TABLE)
        op.drop_table(_TABLE)
    logger.info("v3210 phone log: reverted")
