# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Field-report templates — oe_fieldreports_template table.

Adds the single table backing reusable, project-scoped field-report
templates. A row is a named, ordered set of custom field definitions
(``fields`` JSON) a site team can choose from when creating a report;
the report itself stores the chosen template id + filled values inside
its existing ``metadata`` JSON, so the report table is untouched.

Built-in templates (Daily Site Report, Safety Walk, Progress Report)
are code-defined constants merged in by the service layer — they are
NOT rows, so a fresh install needs no seed.

Idempotent: guarded by an inspector so re-running after SQLite's
``Base.metadata.create_all`` / ``sqlite_auto_migrate`` (dev) is a no-op;
Postgres prod gets the DDL. All ``id`` / ``*_id`` columns are
``String(36)`` to match the platform's ``GUID`` TypeDecorator on
SQLite + PostgreSQL.

Revision ID: v3044_fieldreport_templates
Revises: v3043_crm_project_link
Created: 2026-05-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3044_fieldreport_templates"
down_revision: Union[str, Sequence[str], None] = "v3043_crm_project_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_fieldreports_template"


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    """Create the oe_fieldreports_template table (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, _TABLE):
        return

    op.create_table(
        _TABLE,
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
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "report_type",
            sa.String(length=30),
            nullable=False,
            server_default="daily",
        ),
        sa.Column("fields", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_oe_fieldreports_template_project_id",
        _TABLE,
        ["project_id"],
    )
    op.create_index(
        "ix_oe_fieldreports_template_project",
        _TABLE,
        ["project_id"],
    )


def downgrade() -> None:
    """Drop the oe_fieldreports_template table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_table(inspector, _TABLE):
        op.drop_table(_TABLE)
