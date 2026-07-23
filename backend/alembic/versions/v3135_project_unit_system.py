# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""projects: add unit_system column (Wave 24, task #167).

Adds ``unit_system`` VARCHAR(16) NOT NULL DEFAULT 'metric' to
``oe_projects_project``.  Existing rows receive 'metric' automatically
via the server_default so no data-fill pass is needed.

Allowed values: 'metric' | 'imperial'

Revision ID: v3135_project_unit_system
Revises: v3134_boq_tax_rate
Create Date: 2026-05-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Alembic identifiers
revision = "v3135_project_unit_system"
down_revision = "v3134_boq_tax_rate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add unit_system column to oe_projects_project."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    tables = inspector.get_table_names()
    if "oe_projects_project" not in tables:
        # Fresh install — SQLAlchemy create_all will handle the column.
        return

    existing_cols = {c["name"] for c in inspector.get_columns("oe_projects_project")}
    if "unit_system" not in existing_cols:
        op.add_column(
            "oe_projects_project",
            sa.Column(
                "unit_system",
                sa.String(16),
                nullable=False,
                server_default="metric",
            ),
        )


def downgrade() -> None:
    """Remove unit_system column from oe_projects_project."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("oe_projects_project")}
    if "unit_system" in existing_cols:
        op.drop_column("oe_projects_project", "unit_system")
