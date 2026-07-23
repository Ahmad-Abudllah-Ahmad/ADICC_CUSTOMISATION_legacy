# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Wave 2 Epic A — generic approval-route engine tables.

Adds four polymorphic tables used by every module that needs a routed
multi-step approval workflow (markup sign-off, submittal review, change
order chain, RFI sign-off, contract signature, etc.). The engine itself
is dumb — it just records who decides what and in which order — so a
follow-up migration can retrofit existing per-module approve/reject
endpoints onto the generic ``instances`` table.

Tables
~~~~~~

``oe_approval_routes_route``
    Template definition. Belongs to a project (nullable for tenant-wide
    templates), names the route, declares which target kind ("markup",
    "submittal", "change_order", …) it applies to.

``oe_approval_routes_step``
    Ordered step inside a route. Each step has an ordinal, either a
    role-based approver (``approver_role``) OR a specific user
    (``approver_user_id``) — exactly one of the two is set. The mode
    ("all" / "any" / "majority") describes how multiple approvers at the
    same step are aggregated when the role expands to several users.

``oe_approval_routes_instance``
    A running workflow for a concrete target. Tracks the current step
    ordinal, the lifecycle status (pending / approved / rejected /
    cancelled), and the actor who started it.

``oe_approval_routes_step_state``
    Per-step decision row. One row per (instance, step) — the service
    upserts on decision time. ``decision`` defaults to ``pending`` until
    an approver acts.

Indexes follow the read-heavy hot-paths:

* (project_id, target_kind) on the route table for "list routes for this
  module within this project".
* (target_kind, target_id) on the instance table for "show me the active
  approval workflow on this markup / RFI".
* (instance_id, step_id) UNIQUE on the step-state table so concurrent
  decisions on the same step collide at the DB layer — the service uses
  this as the race-guard.

Idempotent: every CREATE check happens up-front so the migration can be
re-run on a partially-applied installation, and a fresh install that
boots the app first already has the tables via ``Base.metadata.create_all``.

Revision ID: v3147_approval_routes
Revises: v3146_markup_assignee
Create Date: 2026-05-28
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3147_approval_routes"
down_revision: Union[str, None] = "v3146_markup_assignee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def _table_exists(bind: sa.engine.Connection, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def _index_exists(bind: sa.engine.Connection, table: str, index: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(ix["name"] == index for ix in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()

    # ── oe_approval_routes_route ──────────────────────────────────────
    if not _table_exists(bind, "oe_approval_routes_route"):
        op.create_table(
            "oe_approval_routes_route",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("target_kind", sa.String(length=64), nullable=False),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1") if bind.dialect.name == "sqlite" else sa.text("true"),
            ),
            sa.Column(
                "created_by",
                sa.String(length=36),
                sa.ForeignKey("oe_users_user.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if not _index_exists(bind, "oe_approval_routes_route", "ix_approval_route_project_kind"):
        op.create_index(
            "ix_approval_route_project_kind",
            "oe_approval_routes_route",
            ["project_id", "target_kind"],
        )

    # ── oe_approval_routes_step ───────────────────────────────────────
    if not _table_exists(bind, "oe_approval_routes_step"):
        op.create_table(
            "oe_approval_routes_step",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "route_id",
                sa.String(length=36),
                sa.ForeignKey("oe_approval_routes_route.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("ordinal", sa.Integer(), nullable=False),
            sa.Column("approver_role", sa.String(length=64), nullable=True),
            sa.Column(
                "approver_user_id",
                sa.String(length=36),
                sa.ForeignKey("oe_users_user.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "mode",
                sa.String(length=16),
                nullable=False,
                server_default="all",
            ),
            sa.Column("sla_hours", sa.Integer(), nullable=True),
        )
    if not _index_exists(bind, "oe_approval_routes_step", "ix_approval_step_route_ordinal"):
        op.create_index(
            "ix_approval_step_route_ordinal",
            "oe_approval_routes_step",
            ["route_id", "ordinal"],
        )

    # ── oe_approval_routes_instance ───────────────────────────────────
    if not _table_exists(bind, "oe_approval_routes_instance"):
        op.create_table(
            "oe_approval_routes_instance",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "route_id",
                sa.String(length=36),
                sa.ForeignKey("oe_approval_routes_route.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("target_kind", sa.String(length=64), nullable=False),
            sa.Column("target_id", sa.String(length=36), nullable=False),
            sa.Column(
                "current_step_ordinal",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default="pending",
            ),
            sa.Column(
                "started_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "started_by",
                sa.String(length=36),
                sa.ForeignKey("oe_users_user.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if not _index_exists(bind, "oe_approval_routes_instance", "ix_approval_instance_target"):
        op.create_index(
            "ix_approval_instance_target",
            "oe_approval_routes_instance",
            ["target_kind", "target_id"],
        )

    # ── oe_approval_routes_step_state ─────────────────────────────────
    if not _table_exists(bind, "oe_approval_routes_step_state"):
        op.create_table(
            "oe_approval_routes_step_state",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "instance_id",
                sa.String(length=36),
                sa.ForeignKey("oe_approval_routes_instance.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "step_id",
                sa.String(length=36),
                sa.ForeignKey("oe_approval_routes_step.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "approver_user_id",
                sa.String(length=36),
                sa.ForeignKey("oe_users_user.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "decision",
                sa.String(length=16),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "instance_id",
                "step_id",
                "approver_user_id",
                name="uq_approval_step_state_instance_step_user",
            ),
        )
    if not _index_exists(bind, "oe_approval_routes_step_state", "ix_approval_step_state_instance_step"):
        op.create_index(
            "ix_approval_step_state_instance_step",
            "oe_approval_routes_step_state",
            ["instance_id", "step_id"],
        )

    logger.info("v3147 approval_routes: 4 tables ensured")


def downgrade() -> None:
    bind = op.get_bind()

    for table in (
        "oe_approval_routes_step_state",
        "oe_approval_routes_instance",
        "oe_approval_routes_step",
        "oe_approval_routes_route",
    ):
        if _table_exists(bind, table):
            op.drop_table(table)
