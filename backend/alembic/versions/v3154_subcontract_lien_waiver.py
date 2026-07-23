# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""wave3: opt-in lien-waiver requirement on subcontract agreements.

Adds a non-nullable ``requires_lien_waiver`` boolean (default false) to
``oe_subcontractors_agreement``. When set, every payment application under the
agreement must carry a signed lien waiver covering the amount before finance
approval or mark-paid is allowed. Default false keeps existing agreements on
their current behaviour.

The embedded-PostgreSQL runtime adds this column automatically at startup via
``postgres_auto_migrate``; this migration covers external-PostgreSQL
deployments that manage schema with Alembic.

Revision ID: v3154_subcontract_lien_waiver
Revises: v3153_clash_source_links
Create Date: 2026-06-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Alembic identifiers
revision = "v3154_subcontract_lien_waiver"
down_revision = "v3153_clash_source_links"
branch_labels = None
depends_on = None

_TABLE = "oe_subcontractors_agreement"
_COLUMN = "requires_lien_waiver"


def upgrade() -> None:
    """Add the non-nullable ``requires_lien_waiver`` boolean (default false)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    existing_cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    if _COLUMN not in existing_cols:
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    """Drop the ``requires_lien_waiver`` column."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    existing_cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    if _COLUMN in existing_cols:
        op.drop_column(_TABLE, _COLUMN)
