# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site prep (pre-construction mobilisation and site-setup readiness).

Creates the two tables of the site-prep module:

    oe_site_prep_plan  - one mobilisation plan per project (target start, status)
    oe_site_prep_item  - a single readiness item grouped by mobilisation category

Readiness is derived (per-category and overall percentages, the commencement-gate
status, the blocked and overdue lists), never stored. The tables foreign-key into
oe_projects_project by id only (cascade on project delete) and never alter it; an
item optionally references its project's plan (SET NULL on plan delete). GUID
columns are VARCHAR(36) (the app.database.GUID TypeDecorator impl); calendar dates
are DATE; created_by is a nullable GUID. PostgreSQL-only.

The embedded-PostgreSQL runtime materialises these tables via ``create_all`` at
startup, so this migration mainly serves external-PostgreSQL deployments that
manage schema with Alembic. Every step is inspector-guarded, so a re-run (or a DB
the runtime already auto-created) is a no-op. Additive: no existing table is
touched. Chained after v3240_site_inventory to keep a single linear head.

Revision ID: v3241_site_prep
Revises: v3240_site_inventory
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3241_site_prep"
down_revision = "v3240_site_inventory"
branch_labels = None
depends_on = None

_PLAN = "oe_site_prep_plan"
_ITEM = "oe_site_prep_item"


def _has_table(name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def _create_plan() -> None:
    if _has_table(_PLAN):
        return
    op.create_table(
        _PLAN,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_start_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", name="uq_site_prep_plan_project"),
    )
    op.create_index("ix_site_prep_plan_project", _PLAN, ["project_id"])


def _create_item() -> None:
    if _has_table(_ITEM):
        return
    op.create_table(
        _ITEM,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            sa.String(length=36),
            sa.ForeignKey("oe_site_prep_plan.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("category", sa.String(length=40), nullable=False, server_default="other"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="not_started"),
        sa.Column("responsible_party", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("completed_date", sa.Date(), nullable=True),
        sa.Column("is_gate", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_site_prep_item_project", _ITEM, ["project_id"])
    op.create_index("ix_site_prep_item_project_category", _ITEM, ["project_id", "category"])
    op.create_index("ix_site_prep_item_project_status", _ITEM, ["project_id", "status"])
    op.create_index("ix_site_prep_item_plan", _ITEM, ["plan_id"])


def upgrade() -> None:
    """Create the site-prep tables (parent before child, idempotent)."""
    _create_plan()
    _create_item()


def downgrade() -> None:
    """Drop the site-prep tables (child before parent, idempotent)."""
    if _has_table(_ITEM):
        op.drop_table(_ITEM)
    if _has_table(_PLAN):
        op.drop_table(_PLAN)
