# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""AI Estimate Builder - initial schema.

Creates the three tables of the oe_ai_estimator module:

    oe_ai_estimator_run    - the long-lived estimate job (FSM status, per-stage
                             checkpoints, detected source / suggested config,
                             resolved provider+model, spend rollup, last
                             validation report, grand total with per-currency
                             subtotals, the BOQ written on apply).
    oe_ai_estimator_group  - one quantity group per run (rolled-up quantities,
                             ElementEnvelope, chosen grounded rate + real score
                             / confidence, resource breakdown, top-K candidates,
                             applied BOQ position).
    oe_ai_estimator_step   - the run's pipeline / ReAct timeline.

The embedded PostgreSQL runtime materialises these via ``create_all`` at
startup, so this migration is for external-PostgreSQL deployments that manage
schema with Alembic. Every CREATE is guarded with ``CREATE TABLE IF NOT
EXISTS`` semantics (table-presence check) so a re-run, or a DB the runtime
already auto-created, is a no-op. PostgreSQL-only - no SQLite shims.

Revision ID: v3170_ai_estimator
Revises: v3169_field_pwa_sync
Create Date: 2026-06-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3170_ai_estimator"
down_revision = "v3169_field_pwa_sync"
branch_labels = None
depends_on = None

_RUN = "oe_ai_estimator_run"
_GROUP = "oe_ai_estimator_group"
_STEP = "oe_ai_estimator_step"


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _pk() -> sa.Column:
    # GUID() stores as String(36); mirror the platform UUID column shape used
    # across the existing table-creation migrations.
    return sa.Column("id", sa.String(36), primary_key=True)


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def _meta() -> sa.Column:
    return sa.Column("metadata", sa.JSON, nullable=False, server_default="{}")


def upgrade() -> None:
    if not _has_table(_RUN):
        op.create_table(
            _RUN,
            _pk(),
            sa.Column(
                "project_id",
                sa.String(36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("user_id", sa.String(36), nullable=False, index=True),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column("agent_name", sa.String(120), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
            sa.Column(
                "current_stage",
                sa.String(24),
                nullable=False,
                server_default="source",
            ),
            sa.Column("checkpoints", sa.JSON, nullable=False, server_default="{}"),
            sa.Column("source_inputs", sa.JSON, nullable=False, server_default="{}"),
            sa.Column("detected_source", sa.JSON, nullable=False, server_default="{}"),
            sa.Column("suggested_config", sa.JSON, nullable=False, server_default="{}"),
            sa.Column("catalogue_id", sa.String(64), nullable=True),
            sa.Column("region", sa.String(32), nullable=True),
            sa.Column("currency", sa.String(8), nullable=True),
            sa.Column("group_by", sa.JSON, nullable=False, server_default="[]"),
            sa.Column("construction_stage", sa.String(32), nullable=True),
            sa.Column("provider", sa.String(40), nullable=True),
            sa.Column("model_used", sa.String(120), nullable=True),
            sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
            sa.Column(
                "cost_usd_estimate",
                sa.Float,
                nullable=False,
                server_default="0.0",
            ),
            sa.Column("duration_ms", sa.Integer, nullable=False, server_default="0"),
            sa.Column("validation_report", sa.JSON, nullable=True),
            sa.Column("grand_total", sa.String(40), nullable=True),
            sa.Column(
                "currency_subtotals",
                sa.JSON,
                nullable=False,
                server_default="{}",
            ),
            sa.Column("completeness_score", sa.Float, nullable=True),
            sa.Column("boq_id", sa.String(36), nullable=True),
            sa.Column("failure_reason", sa.String(255), nullable=True),
            _meta(),
            *_timestamps(),
            sa.Index("ix_ai_estimator_run_project", "project_id"),
            sa.Index("ix_ai_estimator_run_user", "user_id"),
            sa.Index("ix_ai_estimator_run_project_status", "project_id", "status"),
            sa.Index("ix_ai_estimator_run_boq", "boq_id"),
        )

    if not _has_table(_GROUP):
        op.create_table(
            _GROUP,
            _pk(),
            sa.Column(
                "run_id",
                sa.String(36),
                sa.ForeignKey("oe_ai_estimator_run.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("group_key", sa.String(500), nullable=False),
            sa.Column("signature", sa.String(64), nullable=True),
            sa.Column("element_ids", sa.JSON, nullable=False, server_default="[]"),
            sa.Column("element_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("quantities", sa.JSON, nullable=False, server_default="{}"),
            sa.Column("envelope", sa.JSON, nullable=False, server_default="{}"),
            sa.Column("chosen_unit", sa.String(20), nullable=True),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("trade", sa.String(40), nullable=True),
            sa.Column("candidate_id", sa.String(64), nullable=True),
            sa.Column("chosen_code", sa.String(64), nullable=True),
            sa.Column("unit_rate", sa.String(40), nullable=True),
            sa.Column("currency", sa.String(8), nullable=True),
            sa.Column("score", sa.Float, nullable=True),
            sa.Column("confidence", sa.Float, nullable=True),
            sa.Column("confidence_band", sa.String(8), nullable=True),
            sa.Column("resources", sa.JSON, nullable=False, server_default="[]"),
            sa.Column("candidates", sa.JSON, nullable=False, server_default="[]"),
            sa.Column("match_method", sa.String(20), nullable=True),
            sa.Column(
                "status",
                sa.String(16),
                nullable=False,
                server_default="unmatched",
            ),
            sa.Column("boq_position_id", sa.String(36), nullable=True),
            sa.Column("confirmed_by", sa.String(36), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
            _meta(),
            *_timestamps(),
            sa.Index("ix_ai_estimator_group_run_status", "run_id", "status"),
            sa.Index("ix_ai_estimator_group_signature", "signature"),
            sa.Index("ix_ai_estimator_group_boq_position", "boq_position_id"),
        )

    if not _has_table(_STEP):
        op.create_table(
            _STEP,
            _pk(),
            sa.Column(
                "run_id",
                sa.String(36),
                sa.ForeignKey("oe_ai_estimator_run.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("stage", sa.String(24), nullable=False),
            sa.Column("step_idx", sa.Integer, nullable=False, server_default="0"),
            sa.Column("role", sa.String(16), nullable=False),
            sa.Column("content", sa.JSON, nullable=False, server_default="{}"),
            sa.Column("token_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("took_ms", sa.Integer, nullable=True),
            *_timestamps(),
            sa.Index("ix_ai_estimator_step_run", "run_id"),
            sa.Index("ix_ai_estimator_step_run_idx", "run_id", "step_idx"),
        )


def downgrade() -> None:
    if _has_table(_STEP):
        op.drop_table(_STEP)
    if _has_table(_GROUP):
        op.drop_table(_GROUP)
    if _has_table(_RUN):
        op.drop_table(_RUN)
