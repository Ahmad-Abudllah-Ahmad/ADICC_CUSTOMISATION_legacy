# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Vision-LLM plan reading - run table plus measurement provenance columns.

Creates the run table of the vision plan reader (issue #194) and adds three
additive provenance / review columns to the existing PDF takeoff measurement
table:

    oe_ai_takeoff_run            - one pollable vision plan-read job. Tracks the
                                   targeted document / page, the mode, the
                                   provider / model used, the token + USD spend
                                   (for the per-user rolling cost cap), the FSM
                                   status, the proposal / accept counts, and a
                                   JSON validation report.

    oe_takeoff_measurement       - gains source, confidence, review_status so a
                                   plan-read proposal can live as a normal
                                   measurement row, badged and filtered by its
                                   review state. All three have a server_default
                                   so every existing row reads unchanged.

The embedded PostgreSQL runtime materialises new tables via ``create_all`` and
auto-heals missing columns at startup, so this migration is for external
PostgreSQL deployments that manage schema with Alembic. Every step is guarded
with a presence check so a re-run, or a DB the runtime already auto-created, is
a no-op. Additive and backfill-safe. PostgreSQL-only.

Revision ID: v3177_ai_takeoff_plan_read
Revises: v3176_resumable_uploads_init
Create Date: 2026-06-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3177_ai_takeoff_plan_read"
down_revision = "v3176_resumable_uploads_init"
branch_labels = None
depends_on = None

_RUN = "oe_ai_takeoff_run"
_MEASUREMENT = "oe_takeoff_measurement"


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _has_table(_RUN):
        op.create_table(
            _RUN,
            # GUID() stores as String(36); mirror the platform UUID column shape.
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "project_id",
                sa.String(36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("document_id", sa.String(255), nullable=False, server_default=""),
            sa.Column("page", sa.Integer, nullable=False, server_default="1"),
            sa.Column("mode", sa.String(16), nullable=False, server_default="rooms"),
            sa.Column("user_id", sa.String(36), nullable=False, index=True),
            sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
            sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
            sa.Column("scale_pixels_per_unit", sa.Float, nullable=True),
            sa.Column("do_cost_match", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("provider", sa.String(40), nullable=True),
            sa.Column("model_used", sa.String(120), nullable=True),
            sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
            sa.Column("cost_usd_estimate", sa.Float, nullable=False, server_default="0"),
            sa.Column("duration_ms", sa.Integer, nullable=False, server_default="0"),
            sa.Column("proposal_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("accepted_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("validation_report", sa.JSON, nullable=True),
            sa.Column("failure_reason", sa.String(255), nullable=True),
            sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
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
        op.create_index("ix_ai_takeoff_run_project_status", _RUN, ["project_id", "status"])
        op.create_index("ix_ai_takeoff_run_user_created", _RUN, ["user_id", "created_at"])

    # Additive provenance / review columns on the existing measurement table.
    if _has_table(_MEASUREMENT):
        if not _has_column(_MEASUREMENT, "source"):
            op.add_column(
                _MEASUREMENT,
                sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
            )
        if not _has_column(_MEASUREMENT, "confidence"):
            op.add_column(_MEASUREMENT, sa.Column("confidence", sa.Float, nullable=True))
        if not _has_column(_MEASUREMENT, "review_status"):
            op.add_column(
                _MEASUREMENT,
                sa.Column("review_status", sa.String(16), nullable=False, server_default="confirmed"),
            )


def downgrade() -> None:
    if _has_table(_RUN):
        op.drop_table(_RUN)
    for col in ("review_status", "confidence", "source"):
        if _has_column(_MEASUREMENT, col):
            op.drop_column(_MEASUREMENT, col)
