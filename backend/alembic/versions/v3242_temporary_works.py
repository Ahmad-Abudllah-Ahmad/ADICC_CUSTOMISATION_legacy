# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Temporary works (safety-critical temporary-works governance register).

Creates the two tables of the temporary-works module:

    oe_temp_works_item    - one temporary-works item per row (falsework,
                            propping, excavation support, facade retention,
                            crane base, ...), carrying its lifecycle status,
                            design check category and responsible people
    oe_temp_works_permit  - a permit issued against an item by the Temporary
                            Works Coordinator (permit to load / strike /
                            dismantle)

Clearance is derived (per-status and per-category counts, design-clearance
progress, overdue lists, per-item load / strike gate status, and the
bearing-load-without-a-valid-permit breach list), never stored. Both tables
foreign-key into oe_projects_project by id only (cascade on project delete) and
never alter it; a permit additionally foreign-keys into its item (cascade on item
delete) and carries its own project_id so every query is project-scoped without a
join. GUID columns are VARCHAR(36) (the app.database.GUID TypeDecorator impl);
calendar dates are DATE; booleans default false; created_by is a nullable GUID.
Type / status / category columns are plain strings, not DB enums, so a new value
never needs a schema change. PostgreSQL-only.

The embedded-PostgreSQL runtime materialises these tables via ``create_all`` at
startup, so this migration mainly serves external-PostgreSQL deployments that
manage schema with Alembic. Every step is inspector-guarded, so a re-run (or a DB
the runtime already auto-created) is a no-op. Additive: no existing table is
touched. Chained after v3241_site_prep to keep a single linear head.

Revision ID: v3242_temporary_works
Revises: v3241_site_prep
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3242_temporary_works"
down_revision = "v3241_site_prep"
branch_labels = None
depends_on = None

_ITEM = "oe_temp_works_item"
_PERMIT = "oe_temp_works_permit"


def _has_table(name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


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
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tw_type", sa.String(length=40), nullable=False),
        sa.Column("design_check_category", sa.String(length=4), nullable=True),
        sa.Column("designer_name", sa.String(length=255), nullable=True),
        sa.Column("checker_name", sa.String(length=255), nullable=True),
        sa.Column("twc_name", sa.String(length=255), nullable=True),
        sa.Column("twc_user_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="identified"),
        sa.Column("required_load_date", sa.Date(), nullable=True),
        sa.Column("required_strike_date", sa.Date(), nullable=True),
        sa.Column("design_due_date", sa.Date(), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("formwork_assignment_id", sa.String(length=36), nullable=True),
        sa.Column("design_document_id", sa.String(length=36), nullable=True),
        sa.Column("check_certificate_document_id", sa.String(length=36), nullable=True),
        sa.Column("schedule_activity_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "reference", name="uq_temp_works_item_project_reference"),
    )
    op.create_index("ix_temp_works_item_project", _ITEM, ["project_id"])
    op.create_index("ix_temp_works_item_project_status", _ITEM, ["project_id", "status"])
    op.create_index("ix_temp_works_item_project_type", _ITEM, ["project_id", "tw_type"])


def _create_permit() -> None:
    if _has_table(_PERMIT):
        return
    op.create_table(
        _PERMIT,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            sa.String(length=36),
            sa.ForeignKey("oe_temp_works_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("permit_number", sa.String(length=40), nullable=False),
        sa.Column("permit_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("issued_by", sa.String(length=255), nullable=True),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("closed_at", sa.Date(), nullable=True),
        sa.Column("closed_by", sa.String(length=36), nullable=True),
        sa.Column("inspection_id", sa.String(length=36), nullable=True),
        sa.Column(
            "prereq_design_check_accepted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "prereq_inspection_passed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("conditions", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_temp_works_permit_project", _PERMIT, ["project_id"])
    op.create_index("ix_temp_works_permit_item", _PERMIT, ["item_id"])
    op.create_index("ix_temp_works_permit_project_status", _PERMIT, ["project_id", "status"])


def upgrade() -> None:
    """Create the temporary-works tables (parent before child, idempotent)."""
    _create_item()
    _create_permit()


def downgrade() -> None:
    """Drop the temporary-works tables (child before parent, idempotent)."""
    if _has_table(_PERMIT):
        op.drop_table(_PERMIT)
    if _has_table(_ITEM):
        op.drop_table(_ITEM)
