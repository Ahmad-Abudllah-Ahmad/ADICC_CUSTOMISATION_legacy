# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""TOP-30 #14: offline field PWA - inspection geo-capture columns.

The offline field shell can raise a quality inspection in the field with a GPS
fix. To render that inspection on the project Geo Hub map (the same way a field
punch item already does), the inspection row needs a capture-time WGS84 pin.
This migration adds ``geo_lat`` / ``geo_lon`` to ``oe_inspections_inspection``,
mirroring the punchlist geo columns exactly.

The sync ledger (``oe_field_sync_ledger``) and the ``field_source`` marker on
the field diary entry landed earlier in ``v3166_field_sync_ledger``; this
migration only carries the inspection delta, so the two do not overlap.

The embedded PostgreSQL runtime materialises these via ``create_all`` at
startup; this migration covers external-PostgreSQL deployments that manage
schema with Alembic. Both columns are inspector-guarded so a re-run (or a DB the
runtime already auto-created) is a no-op. Nullable + no default - absent means
"no map pin", not "(0, 0)".

Revision ID: v3169_field_pwa_sync
Revises: v3166_field_sync_ledger
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3169_field_pwa_sync"
down_revision = "v3166_field_sync_ledger"
branch_labels = None
depends_on = None

_INSPECTION = "oe_inspections_inspection"


def _cols(insp: sa.Inspector, table: str) -> set[str]:
    try:
        return {c["name"] for c in insp.get_columns(table)}
    except Exception:  # noqa: BLE001 - table absent
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = _cols(insp, _INSPECTION)
    if not cols:
        # Table absent (fresh DB before create_all) - the model carries these
        # columns, so create_all builds them; nothing to do here.
        return
    if "geo_lat" not in cols:
        op.add_column(_INSPECTION, sa.Column("geo_lat", sa.Float(), nullable=True))
    if "geo_lon" not in cols:
        op.add_column(_INSPECTION, sa.Column("geo_lon", sa.Float(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = _cols(insp, _INSPECTION)
    if "geo_lon" in cols:
        op.drop_column(_INSPECTION, "geo_lon")
    if "geo_lat" in cols:
        op.drop_column(_INSPECTION, "geo_lat")
