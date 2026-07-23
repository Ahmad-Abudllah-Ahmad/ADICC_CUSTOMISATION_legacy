# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Handover & Closeout - initial schema.

Creates the three tables of the oe_closeout module:

    oe_closeout_package - one per-project digital handover / closeout package
                          (project type, status, checklist template, the
                          denormalised completeness counters, and the last
                          build stamp).
    oe_closeout_slot    - one checklist requirement inside a package (as-built
                          drawings, O&M manual, warranty, COBie register,
                          punch-closure evidence, inspection certificate,
                          H&S file, ...).
    oe_closeout_binding - links a slot to its evidence: a SOFT cross-link to a
                          CDE document (no hard FK, same convention as
                          ``PunchItem.clash_result_id``), an external URL, or a
                          generated artifact, plus the human sign-off and the
                          AI-suggested-human-confirmed bookkeeping.

The embedded PostgreSQL runtime materialises these via ``create_all`` at
startup, so this migration is for external-PostgreSQL deployments that manage
schema with Alembic. Every CREATE is guarded with a table-presence check so a
re-run, or a DB the runtime already auto-created, is a no-op. PostgreSQL-only -
no SQLite shims.

Revision ID: v3172_closeout_init
Revises: v3171_ai_estimator_intake
Create Date: 2026-06-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3172_closeout_init"
down_revision = "v3171_ai_estimator_intake"
branch_labels = None
depends_on = None

_PACKAGE = "oe_closeout_package"
_SLOT = "oe_closeout_slot"
_BINDING = "oe_closeout_binding"


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


def _meta() -> sa.Column:
    return sa.Column("metadata", sa.JSON, nullable=False, server_default="{}")


def upgrade() -> None:
    if not _has_table(_PACKAGE):
        op.create_table(
            _PACKAGE,
            _pk(),
            sa.Column(
                "project_id",
                sa.String(36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
                index=True,
            ),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column(
                "project_type",
                sa.String(30),
                nullable=False,
                server_default="commercial",
            ),
            sa.Column(
                "status",
                sa.String(20),
                nullable=False,
                server_default="draft",
            ),
            sa.Column("checklist_template", sa.String(60), nullable=False),
            sa.Column(
                "required_slot_count",
                sa.Integer,
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "delivered_slot_count",
                sa.Integer,
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "completeness_pct",
                sa.Integer,
                nullable=False,
                server_default="0",
            ),
            sa.Column("last_built_job_id", sa.String(36), nullable=True),
            sa.Column("last_built_at", sa.String(40), nullable=True),
            sa.Column("package_key", sa.String(1024), nullable=True),
            _meta(),
            *_timestamps(),
            sa.Index("ix_closeout_package_project", "project_id", unique=True),
        )

    if not _has_table(_SLOT):
        op.create_table(
            _SLOT,
            _pk(),
            sa.Column(
                "package_id",
                sa.String(36),
                sa.ForeignKey("oe_closeout_package.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("slot_key", sa.String(60), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("category", sa.String(40), nullable=False, server_default="other"),
            sa.Column("discipline", sa.String(50), nullable=True),
            sa.Column(
                "is_required",
                sa.Boolean,
                nullable=False,
                server_default=sa.text("'0'"),
            ),
            sa.Column(
                "source_kind",
                sa.String(20),
                nullable=False,
                server_default="cde_document",
            ),
            sa.Column("generated_artifact", sa.String(40), nullable=True),
            sa.Column("ordinal", sa.Integer, nullable=False, server_default="0"),
            _meta(),
            *_timestamps(),
            sa.Index("ix_closeout_slot_package", "package_id"),
        )

    if not _has_table(_BINDING):
        op.create_table(
            _BINDING,
            _pk(),
            sa.Column(
                "slot_id",
                sa.String(36),
                sa.ForeignKey("oe_closeout_slot.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            # SOFT cross-link to oe_documents_document - NO hard FK (mirrors
            # PunchItem.clash_result_id) so deleting a document never
            # cascade-wipes the closeout history.
            sa.Column("document_id", sa.String(36), nullable=True),
            sa.Column("external_url", sa.String(1024), nullable=True),
            sa.Column(
                "is_verified",
                sa.Boolean,
                nullable=False,
                server_default=sa.text("'0'"),
            ),
            sa.Column("verified_by", sa.String(36), nullable=True),
            sa.Column("verified_at", sa.String(40), nullable=True),
            sa.Column(
                "suggested_by_ai",
                sa.Boolean,
                nullable=False,
                server_default=sa.text("'0'"),
            ),
            sa.Column("ai_confidence", sa.String(10), nullable=True),
            _meta(),
            *_timestamps(),
            sa.Index("ix_closeout_binding_slot", "slot_id"),
        )


def downgrade() -> None:
    if _has_table(_BINDING):
        op.drop_table(_BINDING)
    if _has_table(_SLOT):
        op.drop_table(_SLOT)
    if _has_table(_PACKAGE):
        op.drop_table(_PACKAGE)
