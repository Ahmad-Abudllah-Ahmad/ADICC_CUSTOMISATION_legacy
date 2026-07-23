# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""AI Estimate Builder - conversational intake (v2) table.

Creates ``oe_ai_estimator_intake``: one row per run (1:1) carrying the
conversational intake FSM state (mode, raw request, detected project type, the
partial / confirmed parameter sheet, per-param status, the clarification round
counter, the current question batch, the transcript, the dialogue phase, and
the composed package-board state).

The embedded PostgreSQL runtime materialises this via ``create_all`` at
startup, so this migration is for external-PostgreSQL deployments that manage
schema with Alembic. The CREATE is guarded with a table-presence check so a
re-run, or a DB the runtime already auto-created, is a no-op. PostgreSQL-only.

Revision ID: v3171_ai_estimator_intake
Revises: v3170_ai_estimator
Create Date: 2026-06-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3171_ai_estimator_intake"
down_revision = "v3170_ai_estimator"
branch_labels = None
depends_on = None

_INTAKE = "oe_ai_estimator_intake"


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def upgrade() -> None:
    if _has_table(_INTAKE):
        return
    op.create_table(
        _INTAKE,
        # GUID() stores as String(36); mirror the platform UUID column shape.
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("oe_ai_estimator_run.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("mode", sa.String(16), nullable=False, server_default="offline"),
        sa.Column("raw_request", sa.Text, nullable=False, server_default=""),
        sa.Column("detected_type", sa.String(40), nullable=True),
        sa.Column("type_confidence", sa.Float, nullable=True),
        sa.Column("params", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("param_status", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("round_idx", sa.Integer, nullable=False, server_default="0"),
        sa.Column("questions", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("transcript", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("phase", sa.String(24), nullable=False, server_default="collect_request"),
        sa.Column("packages", sa.JSON, nullable=False, server_default="[]"),
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
        sa.Index("ix_ai_estimator_intake_run", "run_id", unique=True),
    )


def downgrade() -> None:
    if _has_table(_INTAKE):
        op.drop_table(_INTAKE)
