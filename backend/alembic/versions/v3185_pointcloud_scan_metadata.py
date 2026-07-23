# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Point-cloud header-sniff metadata column.

The reality-capture upload now runs a cheap header sniff the moment the bytes
land (read only the LAS/E57 header, never the point payload) and persists what
it learned: which scalar fields the cloud carries (RGB / intensity /
classification), the declared linear units, the coordinate ranges, the point
format and a sniff status. That summary needs a home, so this migration adds:

    oe_pointcloud_scan_dataset.scan_metadata  - JSON, NOT NULL, default '{}'.

The existing point_count / bbox_json / crs_epsg / crs_confidence columns already
hold the numeric facts the sniff also backfills; only this advisory JSON summary
is new.

The embedded PostgreSQL runtime materialises the column via ``create_all`` at
startup, so this migration is for external PostgreSQL deployments that manage
schema with Alembic. The step is presence-guarded so a re-run, or a DB the
runtime already auto-created, is a no-op. Additive and backfill-safe: existing
rows get the ``'{}'`` server default, no data move. PostgreSQL-only, no SQLite
shims.

Revision ID: v3185_pointcloud_scan_metadata
Revises: v3184_takeoff_area_deduction
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3185_pointcloud_scan_metadata"
down_revision = "v3184_takeoff_area_deduction"
branch_labels = None
depends_on = None

_TABLE = "oe_pointcloud_scan_dataset"
_COLUMN = "scan_metadata"


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if _has_table(_TABLE) and not _has_column(_TABLE, _COLUMN):
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.JSON(),
                nullable=False,
                server_default="{}",
            ),
        )


def downgrade() -> None:
    if _has_column(_TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
