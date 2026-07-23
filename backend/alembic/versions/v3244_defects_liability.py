# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Defects-liability register (post-handover warranty and DLP register).

Creates the two tables of the defects-liability module:

    oe_dlp_warranty - one warranty / defects-liability-period entry per row (a
                      covered element, its responsible subcontractor and work
                      package, the warranty type, the key dates and above all the
                      DLP end date that decides when retention can be released)
    oe_dlp_defect   - one defect notice raised against a warranty while its
                      defects liability period runs (who must fix what by when,
                      and whether it has been rectified)

Retention-release readiness is derived (per-status / per-warranty-type counts,
expiring and expired lists, open and overdue defect load, per-subcontractor
health, overall health score and the retention-release-ready list), never stored.
Both tables foreign-key into oe_projects_project by id only (cascade on project
delete) and never alter it; a defect additionally foreign-keys into its warranty
(cascade on warranty delete) and carries its own project_id so every query is
project-scoped without a join. GUID columns are VARCHAR(36) (the app.database.GUID
TypeDecorator impl); calendar dates are DATE; created_by and the subcontractor /
contract / document / punchlist / ncr soft links are nullable with no foreign key.
Warranty-type / status / severity columns are plain strings, not DB enums, so a
new value never needs a schema change. PostgreSQL-only.

The embedded-PostgreSQL runtime materialises these tables via ``create_all`` at
startup, so this migration mainly serves external-PostgreSQL deployments that
manage schema with Alembic. Every step is inspector-guarded, so a re-run (or a DB
the runtime already auto-created) is a no-op. Additive: no existing table is
touched. Chained after v3243_interface_management to keep a single linear head.

Revision ID: v3244_defects_liability
Revises: v3243_interface_management
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3244_defects_liability"
down_revision = "v3243_interface_management"
branch_labels = None
depends_on = None

_WARRANTY = "oe_dlp_warranty"
_DEFECT = "oe_dlp_defect"


def _has_table(name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def _create_warranty() -> None:
    if _has_table(_WARRANTY):
        return
    op.create_table(
        _WARRANTY,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("element_description", sa.Text(), nullable=True),
        sa.Column("subcontractor_id", sa.String(length=36), nullable=True),
        sa.Column("subcontractor_name", sa.String(length=255), nullable=True),
        sa.Column("work_package", sa.String(length=120), nullable=True),
        sa.Column("warranty_type", sa.String(length=40), nullable=True),
        sa.Column("handover_date", sa.Date(), nullable=True),
        sa.Column("warranty_start_date", sa.Date(), nullable=True),
        sa.Column("warranty_months", sa.Integer(), nullable=True),
        sa.Column("warranty_end_date", sa.Date(), nullable=True),
        sa.Column("dlp_end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="in_dlp"),
        sa.Column("retention_release_date", sa.Date(), nullable=True),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "reference", name="uq_dlp_warranty_project_reference"),
    )
    op.create_index("ix_dlp_warranty_project", _WARRANTY, ["project_id"])
    op.create_index("ix_dlp_warranty_project_status", _WARRANTY, ["project_id", "status"])
    op.create_index(
        "ix_dlp_warranty_project_subcontractor",
        _WARRANTY,
        ["project_id", "subcontractor_id"],
    )


def _create_defect() -> None:
    if _has_table(_DEFECT):
        return
    op.create_table(
        _DEFECT,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "warranty_id",
            sa.String(length=36),
            sa.ForeignKey("oe_dlp_warranty.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=True),
        sa.Column("raised_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("rectified_date", sa.Date(), nullable=True),
        sa.Column("responsible_party", sa.String(length=255), nullable=True),
        sa.Column("punchlist_id", sa.String(length=36), nullable=True),
        sa.Column("ncr_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_dlp_defect_project", _DEFECT, ["project_id"])
    op.create_index("ix_dlp_defect_warranty", _DEFECT, ["warranty_id"])
    op.create_index("ix_dlp_defect_project_status", _DEFECT, ["project_id", "status"])


def upgrade() -> None:
    """Create the defects-liability tables (parent before child, idempotent)."""
    _create_warranty()
    _create_defect()


def downgrade() -> None:
    """Drop the defects-liability tables (child before parent, idempotent)."""
    if _has_table(_DEFECT):
        op.drop_table(_DEFECT)
    if _has_table(_WARRANTY):
        op.drop_table(_WARRANTY)
