# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Resumable Uploads - initial schema.

Creates the single table of the oe_resumable_uploads module:

    oe_resumable_uploads_session - one in-flight chunked upload. Tracks the
                                   declared total size, the fixed chunk size,
                                   the derived chunk count, the set of received
                                   chunk indices (JSON list), an optional client
                                   SHA-256 for integrity, the lifecycle status,
                                   the owning project / user, and the resulting
                                   document id + storage key once assembled.

The embedded PostgreSQL runtime materialises this via ``create_all`` at
startup, so this migration is for external-PostgreSQL deployments that manage
schema with Alembic. The CREATE is guarded with a table-presence check so a
re-run, or a DB the runtime already auto-created, is a no-op. PostgreSQL-only.

Revision ID: v3176_resumable_uploads_init
Revises: v3175_saved_views_init
Create Date: 2026-06-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3176_resumable_uploads_init"
down_revision = "v3175_saved_views_init"
branch_labels = None
depends_on = None

_SESSION = "oe_resumable_uploads_session"


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def upgrade() -> None:
    if _has_table(_SESSION):
        return
    op.create_table(
        _SESSION,
        # GUID() stores as String(36); mirror the platform UUID column shape.
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=False, server_default="other"),
        sa.Column("total_size", sa.Integer, nullable=False),
        sa.Column("chunk_size", sa.Integer, nullable=False),
        sa.Column("total_chunks", sa.Integer, nullable=False),
        sa.Column("received_chunks", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="in_progress"),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("storage_key", sa.String(1024), nullable=True),
        sa.Column("document_id", sa.String(36), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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


def downgrade() -> None:
    if _has_table(_SESSION):
        op.drop_table(_SESSION)
