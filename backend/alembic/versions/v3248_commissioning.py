# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Commissioning (Cx) register - systems, checklists, checklist items, issues.

Creates the four tables of the commissioning module:

    oe_commissioning_system          - a commissionable building system
                                       (HVAC, electrical, fire, ...) with its
                                       lifecycle status and commission stamp
    oe_commissioning_checklist       - a prefunctional or functional checklist
                                       attached to a system
    oe_commissioning_checklist_item  - a single check line within a checklist
                                       (pending / pass / fail / na)
    oe_commissioning_issue           - a deficiency raised against a system;
                                       an open critical issue blocks commission

Readiness (percent of applicable functional items passed, the traffic-light
level and the commission gate) is derived in the service layer, never stored.
The intra-module hierarchy uses real foreign keys with cascade delete
(system -> checklist -> item, system -> issue); external references
(project_id, created_by, verified_by, ...) are plain VARCHAR(36) so the module
loads in minimal fixtures without pulling in the projects / users modules.
GUID columns are VARCHAR(36) (the app.database.GUID TypeDecorator impl); the
commission and result stamps are ISO-8601 strings; type / status / severity /
kind columns are plain strings, not DB enums, so a new value never needs a
schema change. PostgreSQL-only.

The embedded-PostgreSQL runtime materialises these tables via ``create_all`` at
startup, so this migration mainly serves external-PostgreSQL deployments that
manage schema with Alembic. Every step is inspector-guarded, so a re-run (or a
DB the runtime already auto-created) is a no-op. Additive: no existing table is
touched. Chained after v3247_correspondence_status_deadline to keep a single
linear head.

Revision ID: v3248_commissioning
Revises: v3247_correspondence_status_deadline
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3248_commissioning"
down_revision = "v3247_correspondence_status_deadline"
branch_labels = None
depends_on = None

_SYSTEM = "oe_commissioning_system"
_CHECKLIST = "oe_commissioning_checklist"
_ITEM = "oe_commissioning_checklist_item"
_ISSUE = "oe_commissioning_issue"


def _has_table(name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def _create_system() -> None:
    if _has_table(_SYSTEM):
        return
    op.create_table(
        _SYSTEM,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("system_type", sa.String(length=50), nullable=False, server_default="hvac"),
        sa.Column("tag", sa.String(length=100), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="not_started"),
        sa.Column("commissioned_at", sa.String(length=32), nullable=True),
        sa.Column("commissioned_by", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_commissioning_system_project", _SYSTEM, ["project_id"])
    op.create_index("ix_commissioning_system_project_status", _SYSTEM, ["project_id", "status"])
    op.create_index("ix_commissioning_system_project_type", _SYSTEM, ["project_id", "system_type"])


def _create_checklist() -> None:
    if _has_table(_CHECKLIST):
        return
    op.create_table(
        _CHECKLIST,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "system_id",
            sa.String(length=36),
            sa.ForeignKey("oe_commissioning_system.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="prefunctional"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_commissioning_checklist_system", _CHECKLIST, ["system_id"])
    op.create_index("ix_commissioning_checklist_system_kind", _CHECKLIST, ["system_id", "kind"])


def _create_item() -> None:
    if _has_table(_ITEM):
        return
    op.create_table(
        _ITEM,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "checklist_id",
            sa.String(length=36),
            sa.ForeignKey("oe_commissioning_checklist.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("result_note", sa.Text(), nullable=True),
        sa.Column("verified_by", sa.String(length=36), nullable=True),
        sa.Column("verified_at", sa.String(length=32), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_commissioning_item_checklist", _ITEM, ["checklist_id"])
    op.create_index("ix_commissioning_item_checklist_status", _ITEM, ["checklist_id", "status"])


def _create_issue() -> None:
    if _has_table(_ISSUE):
        return
    op.create_table(
        _ISSUE,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "system_id",
            sa.String(length=36),
            sa.ForeignKey("oe_commissioning_system.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("raised_by", sa.String(length=36), nullable=True),
        sa.Column("closed_by", sa.String(length=36), nullable=True),
        sa.Column("closed_at", sa.String(length=32), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_commissioning_issue_system", _ISSUE, ["system_id"])
    op.create_index("ix_commissioning_issue_system_status", _ISSUE, ["system_id", "status"])
    op.create_index("ix_commissioning_issue_system_severity", _ISSUE, ["system_id", "severity"])


def upgrade() -> None:
    """Create the commissioning tables (parents before children, idempotent)."""
    _create_system()
    _create_checklist()
    _create_item()
    _create_issue()


def downgrade() -> None:
    """Drop the commissioning tables (children before parents, idempotent)."""
    if _has_table(_ISSUE):
        op.drop_table(_ISSUE)
    if _has_table(_ITEM):
        op.drop_table(_ITEM)
    if _has_table(_CHECKLIST):
        op.drop_table(_CHECKLIST)
    if _has_table(_SYSTEM):
        op.drop_table(_SYSTEM)
