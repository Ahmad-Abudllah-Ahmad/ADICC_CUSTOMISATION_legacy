# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site inventory (on-site material metering and stock).

Creates the three tables of the site-inventory module:

    oe_site_inventory_location  - a geo-tagged storage location on a project
    oe_site_inventory_item      - a stock item / material record
    oe_site_inventory_movement  - a stock movement (inbound / consumption /
                                  waste / transfer)

Stock on hand is derived (the signed sum of movements), never stored. The tables
foreign-key into existing tables by id only - oe_projects_project (scope),
oe_boq_position (consumption + budget), oe_procurement_goods_receipt and
oe_procurement_req_item (procurement links) - and never alter them. GUID columns
are VARCHAR(36) (the app.database.GUID TypeDecorator impl); money and quantities
are NUMERIC(18, 4); geo coordinates are NUMERIC(9, 6). PostgreSQL-only.

The embedded-PostgreSQL runtime materialises these tables via ``create_all`` at
startup, so this migration mainly serves external-PostgreSQL deployments that
manage schema with Alembic. Every step is inspector-guarded, so a re-run (or a DB
the runtime already auto-created) is a no-op. Additive: no existing table is
touched. Chained after v3239_takeoff_page_scales to keep a single linear head.

Revision ID: v3240_site_inventory
Revises: v3239_takeoff_page_scales
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3240_site_inventory"
down_revision = "v3239_takeoff_page_scales"
branch_labels = None
depends_on = None

_LOCATION = "oe_site_inventory_location"
_ITEM = "oe_site_inventory_item"
_MOVEMENT = "oe_site_inventory_movement"


def _has_table(name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def _create_location() -> None:
    if _has_table(_LOCATION):
        return
    op.create_table(
        _LOCATION,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_site_inv_location_project", _LOCATION, ["project_id"])


def _create_item() -> None:
    if _has_table(_ITEM):
        return
    op.create_table(
        _ITEM,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=False, server_default=""),
        sa.Column(
            "boq_position_id",
            sa.String(length=36),
            sa.ForeignKey("oe_boq_position.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "procurement_req_item_id",
            sa.String(length=36),
            sa.ForeignKey("oe_procurement_req_item.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "default_location_id",
            sa.String(length=36),
            sa.ForeignKey("oe_site_inventory_location.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("standard_unit_cost", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("reorder_point", sa.Numeric(18, 4), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_site_inv_item_project", _ITEM, ["project_id"])
    op.create_index("ix_site_inv_item_boq_position", _ITEM, ["boq_position_id"])


def _create_movement() -> None:
    if _has_table(_MOVEMENT):
        return
    op.create_table(
        _MOVEMENT,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            sa.String(length=36),
            sa.ForeignKey("oe_site_inventory_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("movement_type", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default=""),
        sa.Column(
            "location_id",
            sa.String(length=36),
            sa.ForeignKey("oe_site_inventory_location.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "to_location_id",
            sa.String(length=36),
            sa.ForeignKey("oe_site_inventory_location.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "boq_position_id",
            sa.String(length=36),
            sa.ForeignKey("oe_boq_position.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "goods_receipt_id",
            sa.String(length=36),
            sa.ForeignKey("oe_procurement_goods_receipt.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_site_inv_move_project_item", _MOVEMENT, ["project_id", "item_id"])
    op.create_index("ix_site_inv_move_project_type", _MOVEMENT, ["project_id", "movement_type"])
    op.create_index("ix_site_inv_move_project_occurred", _MOVEMENT, ["project_id", "occurred_at"])
    op.create_index("ix_site_inv_move_boq_position", _MOVEMENT, ["boq_position_id"])


def upgrade() -> None:
    """Create the site-inventory tables (parents before children, idempotent)."""
    _create_location()
    _create_item()
    _create_movement()


def downgrade() -> None:
    """Drop the site-inventory tables (children before parents, idempotent)."""
    if _has_table(_MOVEMENT):
        op.drop_table(_MOVEMENT)
    if _has_table(_ITEM):
        op.drop_table(_ITEM)
    if _has_table(_LOCATION):
        op.drop_table(_LOCATION)
