# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Saved Views - initial schema.

Creates the two tables of the oe_saved_views module:

    oe_saved_views_view - one named, scoped filter spec against a registered
                          entity. The ``spec`` JSON is the serialized FilterSpec;
                          ``share_scope`` is private / project / workspace (never
                          public). A unique constraint stops two identically
                          named views in the same scope for the same owner.
    oe_saved_views_run  - append-only audit/telemetry of a run, so budget
                          overflow attempts and slow views are observable.

The embedded PostgreSQL runtime materialises these via ``create_all`` at
startup, so this migration is for external-PostgreSQL deployments that manage
schema with Alembic. Every CREATE is guarded with a table-presence check so a
re-run, or a DB the runtime already auto-created, is a no-op. PostgreSQL-only -
no SQLite shims.

Revision ID: v3175_saved_views_init
Revises: v3174_pointcloud_init
Create Date: 2026-06-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3175_saved_views_init"
down_revision = "v3174_pointcloud_init"
branch_labels = None
depends_on = None

_VIEW = "oe_saved_views_view"
_RUN = "oe_saved_views_run"


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _pk() -> sa.Column:
    # GUID() stores as String(36); mirror the platform UUID column shape used
    # across the existing table-creation migrations.
    return sa.Column("id", sa.String(36), primary_key=True)


def _timestamps() -> list[sa.Column]:
    # Base mixin provides created_at / updated_at with a DB-side now() default.
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


def upgrade() -> None:
    if not _has_table(_VIEW):
        op.create_table(
            _VIEW,
            _pk(),
            sa.Column(
                "owner_id",
                sa.String(36),
                sa.ForeignKey("oe_users_user.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "project_id",
                sa.String(36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=True,
                index=True,
            ),
            sa.Column("entity_type", sa.String(64), nullable=False, index=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("spec", sa.JSON, nullable=False, server_default="{}"),
            sa.Column(
                "share_scope",
                sa.String(16),
                nullable=False,
                server_default="private",
            ),
            sa.Column(
                "is_pinned",
                sa.Boolean,
                nullable=False,
                server_default="0",
            ),
            sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
            *_timestamps(),
            sa.Index("ix_saved_views_owner_entity", "owner_id", "entity_type"),
            sa.Index("ix_saved_views_project_entity", "project_id", "entity_type"),
            sa.UniqueConstraint(
                "owner_id",
                "project_id",
                "entity_type",
                "name",
                name="uq_saved_views_owner_scope_name",
            ),
        )

    if not _has_table(_RUN):
        op.create_table(
            _RUN,
            _pk(),
            sa.Column(
                "saved_view_id",
                sa.String(36),
                sa.ForeignKey("oe_saved_views_view.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
            sa.Column("owner_id", sa.String(36), nullable=False, index=True),
            sa.Column("entity_type", sa.String(64), nullable=False),
            sa.Column("row_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("truncated", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("elapsed_ms", sa.Integer, nullable=False, server_default="0"),
            sa.Column("outcome", sa.String(16), nullable=False, server_default="ok"),
            sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
            *_timestamps(),
            sa.Index("ix_saved_views_run_view_created", "saved_view_id", "created_at"),
        )


def downgrade() -> None:
    if _has_table(_RUN):
        op.drop_table(_RUN)
    if _has_table(_VIEW):
        op.drop_table(_VIEW)
