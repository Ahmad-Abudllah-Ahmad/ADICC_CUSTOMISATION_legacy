# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""BOQ per-position AI copilot messages.

Adds ``oe_boq_position_copilot_message`` - one row per turn in a BOQ
position's AI copilot thread (the user's message or the assistant's reply),
carrying any structured action proposals the assistant produced.

The embedded PostgreSQL runtime materialises this via ``create_all`` (new
table), so this migration is for external-PostgreSQL deployments that manage
schema with Alembic. Every step is guarded with a presence check so a re-run,
or a DB the runtime already auto-created, is a no-op. Additive and
backfill-safe (no existing data is touched). PostgreSQL-only.

``actions`` is created as JSONB to match the model's generic-JSON -> JSONB DDL
rewrite (app.core.pg_optimizations), so the on-disk type agrees with what
``create_all`` produces on the embedded runtime.

Revision ID: v3182_boq_position_copilot
Revises: v3181_cost_catalogs
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v3182_boq_position_copilot"
down_revision = "v3181_cost_catalogs"
branch_labels = None
depends_on = None

_TABLE = "oe_boq_position_copilot_message"
_POSITION_TABLE = "oe_boq_position"
_IX_POSITION = "ix_oe_boq_position_copilot_message_position_id"
_IX_BOQ = "ix_oe_boq_position_copilot_message_boq_id"
_IX_PROJECT = "ix_oe_boq_position_copilot_message_project_id"
_IX_POSITION_CREATED = "ix_boq_copilot_position_created"
_IX_BOQ_CREATED = "ix_boq_copilot_boq_created"


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _has_index(table: str, index: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(ix["name"] == index for ix in insp.get_indexes(table))


def upgrade() -> None:
    if not _has_table(_TABLE):
        op.create_table(
            _TABLE,
            # GUID() stores as String(36); mirror the platform UUID column shape.
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "position_id",
                sa.String(36),
                sa.ForeignKey(f"{_POSITION_TABLE}.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("boq_id", sa.String(36), nullable=False),
            sa.Column("project_id", sa.String(36), nullable=False),
            sa.Column("role", sa.String(16), nullable=False),
            sa.Column("content", sa.Text, nullable=False, server_default=""),
            # JSONB to match the model's generic-JSON -> JSONB DDL rewrite.
            sa.Column("actions", postgresql.JSONB, nullable=True),
            sa.Column("created_by", sa.String(36), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    # Single-column FK/lookup indexes (mirror the model's index=True columns).
    if not _has_index(_TABLE, _IX_POSITION):
        op.create_index(_IX_POSITION, _TABLE, ["position_id"])
    if not _has_index(_TABLE, _IX_BOQ):
        op.create_index(_IX_BOQ, _TABLE, ["boq_id"])
    if not _has_index(_TABLE, _IX_PROJECT):
        op.create_index(_IX_PROJECT, _TABLE, ["project_id"])
    # Composite hot-path indexes (per-position thread / per-BOQ audit feed).
    if not _has_index(_TABLE, _IX_POSITION_CREATED):
        op.create_index(_IX_POSITION_CREATED, _TABLE, ["position_id", "created_at"])
    if not _has_index(_TABLE, _IX_BOQ_CREATED):
        op.create_index(_IX_BOQ_CREATED, _TABLE, ["boq_id", "created_at"])


def downgrade() -> None:
    for ix in (
        _IX_BOQ_CREATED,
        _IX_POSITION_CREATED,
        _IX_PROJECT,
        _IX_BOQ,
        _IX_POSITION,
    ):
        if _has_index(_TABLE, ix):
            op.drop_index(ix, table_name=_TABLE)
    if _has_table(_TABLE):
        op.drop_table(_TABLE)
