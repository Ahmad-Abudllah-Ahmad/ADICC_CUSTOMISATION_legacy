# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Interface register (multi-package coordination register).

Creates the two tables of the interface-management module:

    oe_interface_mgmt_interface - one interface (handshake) per row between two
                                  parties, disciplines or work packages, carrying
                                  its status, priority, type, owning and accepting
                                  side, and key dates
    oe_interface_mgmt_action    - one action needed to close an interface (who
                                  does what by when)

The register numbers are derived (per-status / per-priority / per-type counts,
overdue and disputed lists, agreed percentage, open action load, per-work-package
health and the overall health score), never stored. Both tables foreign-key into
oe_projects_project by id only (cascade on project delete) and never alter it; an
action additionally foreign-keys into its interface (cascade on interface delete)
and carries its own project_id so every query is project-scoped without a join.
GUID columns are VARCHAR(36) (the app.database.GUID TypeDecorator impl); calendar
dates are DATE; created_by and the subcontractor / schedule soft links are
nullable GUIDs with no foreign key. Type / status / priority columns are plain
strings, not DB enums, so a new value never needs a schema change. PostgreSQL-only.

The embedded-PostgreSQL runtime materialises these tables via ``create_all`` at
startup, so this migration mainly serves external-PostgreSQL deployments that
manage schema with Alembic. Every step is inspector-guarded, so a re-run (or a DB
the runtime already auto-created) is a no-op. Additive: no existing table is
touched. Chained after v3242_temporary_works to keep a single linear head.

Revision ID: v3243_interface_management
Revises: v3242_temporary_works
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3243_interface_management"
down_revision = "v3242_temporary_works"
branch_labels = None
depends_on = None

_INTERFACE = "oe_interface_mgmt_interface"
_ACTION = "oe_interface_mgmt_action"


def _has_table(name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def _create_interface() -> None:
    if _has_table(_INTERFACE):
        return
    op.create_table(
        _INTERFACE,
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
        sa.Column("owner_party", sa.String(length=255), nullable=True),
        sa.Column("owner_subcontractor_id", sa.String(length=36), nullable=True),
        sa.Column("accepter_party", sa.String(length=255), nullable=True),
        sa.Column("accepter_subcontractor_id", sa.String(length=36), nullable=True),
        sa.Column("discipline_from", sa.String(length=60), nullable=True),
        sa.Column("discipline_to", sa.String(length=60), nullable=True),
        sa.Column("work_package_from", sa.String(length=120), nullable=True),
        sa.Column("work_package_to", sa.String(length=120), nullable=True),
        sa.Column("interface_type", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="identified"),
        sa.Column("priority", sa.String(length=20), nullable=True),
        sa.Column("need_by_date", sa.Date(), nullable=True),
        sa.Column("agreed_date", sa.Date(), nullable=True),
        sa.Column("closed_date", sa.Date(), nullable=True),
        sa.Column("rfi_id", sa.String(length=36), nullable=True),
        sa.Column("schedule_activity_id", sa.String(length=36), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "reference", name="uq_interface_mgmt_project_reference"),
    )
    op.create_index("ix_interface_mgmt_interface_project", _INTERFACE, ["project_id"])
    op.create_index("ix_interface_mgmt_interface_project_status", _INTERFACE, ["project_id", "status"])
    op.create_index(
        "ix_interface_mgmt_interface_project_owner",
        _INTERFACE,
        ["project_id", "owner_subcontractor_id"],
    )


def _create_action() -> None:
    if _has_table(_ACTION):
        return
    op.create_table(
        _ACTION,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "interface_id",
            sa.String(length=36),
            sa.ForeignKey("oe_interface_mgmt_interface.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("action_party", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("completed_date", sa.Date(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_interface_mgmt_action_project", _ACTION, ["project_id"])
    op.create_index("ix_interface_mgmt_action_interface", _ACTION, ["interface_id"])
    op.create_index("ix_interface_mgmt_action_project_status", _ACTION, ["project_id", "status"])


def upgrade() -> None:
    """Create the interface-register tables (parent before child, idempotent)."""
    _create_interface()
    _create_action()


def downgrade() -> None:
    """Drop the interface-register tables (child before parent, idempotent)."""
    if _has_table(_ACTION):
        op.drop_table(_ACTION)
    if _has_table(_INTERFACE):
        op.drop_table(_INTERFACE)
