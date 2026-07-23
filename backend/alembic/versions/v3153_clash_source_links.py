# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""wave1: link auto-created punch items and NCRs back to their source clash.

Adds a nullable, indexed ``clash_result_id`` to ``oe_punchlist_item`` and
``oe_ncr_ncr``. When the clash engine reports a high-severity interference the
punchlist and NCR modules now auto-create a record and stamp this column with
the originating ClashResult.id. That same column makes the auto-creation
idempotent (one punch item / one NCR per clash result). Absent means the
record was not clash-sourced.

The embedded-PostgreSQL runtime adds these columns automatically at startup via
``postgres_auto_migrate``; this migration covers external-PostgreSQL
deployments that manage schema with Alembic.

Revision ID: v3153_clash_source_links
Revises: v3152_ai_agents_custom
Create Date: 2026-06-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Alembic identifiers
revision = "v3153_clash_source_links"
down_revision = "v3152_ai_agents_custom"
branch_labels = None
depends_on = None

# (table, column, index name) - index name matches SQLAlchemy's index=True default
_COLUMNS = (
    ("oe_punchlist_item", "clash_result_id", "ix_oe_punchlist_item_clash_result_id"),
    ("oe_ncr_ncr", "clash_result_id", "ix_oe_ncr_ncr_clash_result_id"),
)


def upgrade() -> None:
    """Add the nullable indexed ``clash_result_id`` column to both tables."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table, column, index in _COLUMNS:
        if table not in tables:
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table)}
        if column not in existing_cols:
            op.add_column(table, sa.Column(column, sa.String(length=36), nullable=True))
        existing_idx = {ix["name"] for ix in inspector.get_indexes(table)}
        if index not in existing_idx:
            op.create_index(index, table, [column])


def downgrade() -> None:
    """Drop the ``clash_result_id`` column and its index from both tables."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table, column, index in _COLUMNS:
        if table not in tables:
            continue
        existing_idx = {ix["name"] for ix in inspector.get_indexes(table)}
        if index in existing_idx:
            op.drop_index(index, table_name=table)
        existing_cols = {c["name"] for c in inspector.get_columns(table)}
        if column in existing_cols:
            op.drop_column(table, column)
