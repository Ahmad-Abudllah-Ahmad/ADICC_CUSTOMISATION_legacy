# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""supplier_catalogs — vendor master, catalog, PR/PO/GR/invoice, warehouse stock.

Adds 16 tables in the ``oe_supplier_catalogs_`` namespace.

Idempotent — re-applying on a DB where ``Base.metadata.create_all`` has
already created the tables is a no-op.

Revision ID: v3025_supplier_catalogs
Revises: v3024_qms
Create Date: 2026-05-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3025_supplier_catalogs"
down_revision: Union[str, Sequence[str], None] = "v3024_qms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table_name, has_unique_code_index)
_TABLES: tuple[str, ...] = (
    "oe_supplier_catalogs_vendor",
    "oe_supplier_catalogs_item_category",
    "oe_supplier_catalogs_catalog_item",
    "oe_supplier_catalogs_price_list",
    "oe_supplier_catalogs_catalog_entry",
    "oe_supplier_catalogs_pr",
    "oe_supplier_catalogs_pr_line",
    "oe_supplier_catalogs_po",
    "oe_supplier_catalogs_po_line",
    "oe_supplier_catalogs_gr",
    "oe_supplier_catalogs_gr_line",
    "oe_supplier_catalogs_invoice",
    "oe_supplier_catalogs_match_record",
    "oe_supplier_catalogs_warehouse",
    "oe_supplier_catalogs_stock_balance",
    "oe_supplier_catalogs_stock_movement",
)


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _has_index(
    inspector: sa.engine.reflection.Inspector,
    table: str,
    index: str,
) -> bool:
    if not _has_table(inspector, table):
        return False
    return any(ix["name"] == index for ix in inspector.get_indexes(table))


def _create_index_safe(
    inspector: sa.engine.reflection.Inspector,
    name: str,
    table: str,
    cols: list[str],
    unique: bool = False,
) -> None:
    if _has_table(inspector, table) and not _has_index(inspector, table, name):
        try:
            op.create_index(name, table, cols, unique=unique)
        except sa.exc.OperationalError:
            pass


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    is_sqlite = bind.dialect.name == "sqlite"
    guid = sa.String(36) if is_sqlite else sa.dialects.postgresql.UUID(as_uuid=True)

    # ── Vendor ────────────────────────────────────────────────────────────────
    if not _has_table(inspector, "oe_supplier_catalogs_vendor"):
        op.create_table(
            "oe_supplier_catalogs_vendor",
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column("code", sa.String(50), nullable=False, unique=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("legal_name", sa.String(255), nullable=True),
            sa.Column("tax_id", sa.String(100), nullable=True),
            sa.Column("contact_id", sa.String(36), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="active"),
            sa.Column("currency", sa.String(10), nullable=False, server_default="EUR"),
            sa.Column("payment_terms_days", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("rating", sa.Integer(), nullable=True),
            sa.Column("country_code", sa.String(8), nullable=True),
            sa.Column("region", sa.String(64), nullable=True),
            sa.Column("categories_json", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("preferred_for_json", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("contacts_json", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("notes", sa.Text(), nullable=True),
        )

    # ── Item category ────────────────────────────────────────────────────────
    if not _has_table(inspector, "oe_supplier_catalogs_item_category"):
        op.create_table(
            "oe_supplier_catalogs_item_category",
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column("code", sa.String(64), nullable=False, unique=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column(
                "parent_id",
                guid,
                sa.ForeignKey("oe_supplier_catalogs_item_category.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("classification_ref", sa.String(64), nullable=True),
        )

    # ── Catalog item ─────────────────────────────────────────────────────────
    if not _has_table(inspector, "oe_supplier_catalogs_catalog_item"):
        op.create_table(
            "oe_supplier_catalogs_catalog_item",
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column("sku", sa.String(100), nullable=False, unique=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "category_id",
                guid,
                sa.ForeignKey("oe_supplier_catalogs_item_category.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("unit_of_measure", sa.String(20), nullable=False, server_default="pcs"),
            sa.Column("manufacturer", sa.String(255), nullable=True),
            sa.Column("mpn", sa.String(100), nullable=True),
            sa.Column("spec_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("hazard_class", sa.String(50), nullable=True),
            sa.Column("shelf_life_days", sa.Integer(), nullable=True),
            sa.Column("reorder_point", sa.Numeric(18, 4), nullable=False, server_default="0"),
            # PostgreSQL rejects an integer default on a boolean column;
            # "1" worked only under SQLite's loose typing.
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )

    # ── Price list ───────────────────────────────────────────────────────────
    if not _has_table(inspector, "oe_supplier_catalogs_price_list"):
        op.create_table(
            "oe_supplier_catalogs_price_list",
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "vendor_id", guid, sa.ForeignKey("oe_supplier_catalogs_vendor.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("valid_from", sa.String(20), nullable=True),
            sa.Column("valid_to", sa.String(20), nullable=True),
            sa.Column("currency", sa.String(10), nullable=False, server_default="EUR"),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("uploaded_by", sa.String(36), nullable=True),
        )

    # ── Catalog entry (price) ────────────────────────────────────────────────
    if not _has_table(inspector, "oe_supplier_catalogs_catalog_entry"):
        op.create_table(
            "oe_supplier_catalogs_catalog_entry",
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "price_list_id",
                guid,
                sa.ForeignKey("oe_supplier_catalogs_price_list.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "catalog_item_id",
                guid,
                sa.ForeignKey("oe_supplier_catalogs_catalog_item.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("vendor_sku", sa.String(100), nullable=True),
            sa.Column("unit_price", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("min_order_qty", sa.Numeric(18, 4), nullable=False, server_default="1"),
            sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default="7"),
            sa.Column("last_purchased_at", sa.String(30), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.UniqueConstraint(
                "price_list_id",
                "catalog_item_id",
                name="uq_supplier_catalogs_entry_pricelist_item",
            ),
        )

    # ── PR ───────────────────────────────────────────────────────────────────
    if not _has_table(inspector, "oe_supplier_catalogs_pr"):
        op.create_table(
            "oe_supplier_catalogs_pr",
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column("number", sa.String(50), nullable=False, unique=True),
            sa.Column("project_id", guid, nullable=False),
            sa.Column("requested_by", sa.String(36), nullable=True),
            sa.Column("requested_at", sa.String(30), nullable=True),
            sa.Column("needed_by", sa.String(20), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("total_estimate", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(10), nullable=False, server_default="EUR"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("approval_chain_json", sa.JSON(), nullable=False, server_default="[]"),
        )

    if not _has_table(inspector, "oe_supplier_catalogs_pr_line"):
        op.create_table(
            "oe_supplier_catalogs_pr_line",
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column("pr_id", guid, sa.ForeignKey("oe_supplier_catalogs_pr.id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "catalog_item_id",
                guid,
                sa.ForeignKey("oe_supplier_catalogs_catalog_item.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("description", sa.String(500), nullable=False),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="1"),
            sa.Column("unit_of_measure", sa.String(20), nullable=False, server_default="pcs"),
            sa.Column("estimated_unit_price", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("estimated_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        )

    # ── PO ───────────────────────────────────────────────────────────────────
    if not _has_table(inspector, "oe_supplier_catalogs_po"):
        op.create_table(
            "oe_supplier_catalogs_po",
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column("number", sa.String(50), nullable=False, unique=True),
            sa.Column(
                "vendor_id", guid, sa.ForeignKey("oe_supplier_catalogs_vendor.id", ondelete="RESTRICT"), nullable=False
            ),
            sa.Column("project_id", guid, nullable=False),
            sa.Column("contract_id", sa.String(36), nullable=True),
            sa.Column("pr_id", guid, sa.ForeignKey("oe_supplier_catalogs_pr.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("order_date", sa.String(20), nullable=True),
            sa.Column("expected_delivery", sa.String(20), nullable=True),
            sa.Column("currency", sa.String(10), nullable=False, server_default="EUR"),
            sa.Column("subtotal", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("tax", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("total", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("terms", sa.Text(), nullable=True),
        )

    if not _has_table(inspector, "oe_supplier_catalogs_po_line"):
        op.create_table(
            "oe_supplier_catalogs_po_line",
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column("po_id", guid, sa.ForeignKey("oe_supplier_catalogs_po.id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "catalog_item_id",
                guid,
                sa.ForeignKey("oe_supplier_catalogs_catalog_item.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("description", sa.String(500), nullable=False),
            sa.Column("ordered_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("unit_of_measure", sa.String(20), nullable=False, server_default="pcs"),
            sa.Column("unit_price", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("line_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("received_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("invoiced_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
        )

    # ── Warehouse (needed before GR FK) ──────────────────────────────────────
    if not _has_table(inspector, "oe_supplier_catalogs_warehouse"):
        op.create_table(
            "oe_supplier_catalogs_warehouse",
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column("code", sa.String(50), nullable=False, unique=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("project_id", guid, nullable=True),
            sa.Column("address", sa.Text(), nullable=True),
            sa.Column("manager_user_id", sa.String(36), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        )

    # ── GR ───────────────────────────────────────────────────────────────────
    if not _has_table(inspector, "oe_supplier_catalogs_gr"):
        op.create_table(
            "oe_supplier_catalogs_gr",
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column("number", sa.String(50), nullable=False, unique=True),
            sa.Column("po_id", guid, sa.ForeignKey("oe_supplier_catalogs_po.id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "warehouse_id",
                guid,
                sa.ForeignKey("oe_supplier_catalogs_warehouse.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("received_at", sa.String(30), nullable=True),
            sa.Column("received_by", sa.String(36), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("scan_method", sa.String(20), nullable=False, server_default="manual"),
            sa.Column("photos_json", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("discrepancy_notes", sa.Text(), nullable=True),
        )

    if not _has_table(inspector, "oe_supplier_catalogs_gr_line"):
        op.create_table(
            "oe_supplier_catalogs_gr_line",
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column("gr_id", guid, sa.ForeignKey("oe_supplier_catalogs_gr.id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "po_line_id", guid, sa.ForeignKey("oe_supplier_catalogs_po_line.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column("received_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("accepted_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("rejected_qty", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("batch_lot", sa.String(100), nullable=True),
            sa.Column("serial_numbers_json", sa.JSON(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
        )

    # ── Invoice ──────────────────────────────────────────────────────────────
    if not _has_table(inspector, "oe_supplier_catalogs_invoice"):
        op.create_table(
            "oe_supplier_catalogs_invoice",
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column("number", sa.String(100), nullable=False),
            sa.Column(
                "vendor_id", guid, sa.ForeignKey("oe_supplier_catalogs_vendor.id", ondelete="RESTRICT"), nullable=False
            ),
            sa.Column("po_id", guid, sa.ForeignKey("oe_supplier_catalogs_po.id", ondelete="SET NULL"), nullable=True),
            sa.Column("invoice_date", sa.String(20), nullable=True),
            sa.Column("due_date", sa.String(20), nullable=True),
            sa.Column("currency", sa.String(10), nullable=False, server_default="EUR"),
            sa.Column("subtotal", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("tax", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("total", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("status", sa.String(32), nullable=False, server_default="received"),
            sa.Column("three_way_match_status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("exception_reason", sa.Text(), nullable=True),
        )

    if not _has_table(inspector, "oe_supplier_catalogs_match_record"):
        op.create_table(
            "oe_supplier_catalogs_match_record",
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "invoice_id", guid, sa.ForeignKey("oe_supplier_catalogs_invoice.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column("po_id", guid, sa.ForeignKey("oe_supplier_catalogs_po.id", ondelete="CASCADE"), nullable=False),
            sa.Column("gr_id", guid, sa.ForeignKey("oe_supplier_catalogs_gr.id", ondelete="SET NULL"), nullable=True),
            sa.Column("matched_at", sa.String(30), nullable=True),
            sa.Column("matched_by", sa.String(36), nullable=True),
            sa.Column("price_variance", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("qty_variance", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("status", sa.String(32), nullable=False, server_default="auto_matched"),
            sa.Column("tolerance_used_pct", sa.Numeric(8, 4), nullable=False, server_default="2.0"),
            sa.Column("notes", sa.Text(), nullable=True),
        )

    if not _has_table(inspector, "oe_supplier_catalogs_stock_balance"):
        op.create_table(
            "oe_supplier_catalogs_stock_balance",
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "warehouse_id",
                guid,
                sa.ForeignKey("oe_supplier_catalogs_warehouse.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "catalog_item_id",
                guid,
                sa.ForeignKey("oe_supplier_catalogs_catalog_item.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("batch_lot", sa.String(100), nullable=False, server_default=""),
            sa.Column("quantity_on_hand", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("quantity_reserved", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("unit_cost_avg", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("last_movement_at", sa.String(30), nullable=True),
            sa.UniqueConstraint(
                "warehouse_id",
                "catalog_item_id",
                "batch_lot",
                name="uq_supplier_catalogs_balance_wh_item_batch",
            ),
        )

    if not _has_table(inspector, "oe_supplier_catalogs_stock_movement"):
        op.create_table(
            "oe_supplier_catalogs_stock_movement",
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
            ),
            sa.Column(
                "warehouse_id",
                guid,
                sa.ForeignKey("oe_supplier_catalogs_warehouse.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "catalog_item_id",
                guid,
                sa.ForeignKey("oe_supplier_catalogs_catalog_item.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("movement_type", sa.String(20), nullable=False),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("reference_type", sa.String(32), nullable=True),
            sa.Column("reference_id", sa.String(36), nullable=True),
            sa.Column("batch_lot", sa.String(100), nullable=True),
            sa.Column("project_id", guid, nullable=True),
            sa.Column("performed_by", sa.String(36), nullable=True),
            sa.Column("performed_at", sa.String(30), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        )

    # Refresh inspector after creates.
    inspector = sa.inspect(bind)

    # Common indexes per table.
    _create_index_safe(inspector, "ix_supplier_catalogs_vendor_status", "oe_supplier_catalogs_vendor", ["status"])
    _create_index_safe(inspector, "ix_supplier_catalogs_vendor_code", "oe_supplier_catalogs_vendor", ["code"])
    _create_index_safe(inspector, "ix_supplier_catalogs_cat_code", "oe_supplier_catalogs_item_category", ["code"])
    _create_index_safe(
        inspector, "ix_supplier_catalogs_cat_parent", "oe_supplier_catalogs_item_category", ["parent_id"]
    )
    _create_index_safe(inspector, "ix_supplier_catalogs_item_sku", "oe_supplier_catalogs_catalog_item", ["sku"])
    _create_index_safe(
        inspector, "ix_supplier_catalogs_item_category", "oe_supplier_catalogs_catalog_item", ["category_id"]
    )
    _create_index_safe(
        inspector, "ix_supplier_catalogs_pricelist_vendor", "oe_supplier_catalogs_price_list", ["vendor_id"]
    )
    _create_index_safe(
        inspector, "ix_supplier_catalogs_entry_pl", "oe_supplier_catalogs_catalog_entry", ["price_list_id"]
    )
    _create_index_safe(
        inspector, "ix_supplier_catalogs_entry_item", "oe_supplier_catalogs_catalog_entry", ["catalog_item_id"]
    )
    _create_index_safe(inspector, "ix_supplier_catalogs_pr_number", "oe_supplier_catalogs_pr", ["number"])
    _create_index_safe(inspector, "ix_supplier_catalogs_pr_project", "oe_supplier_catalogs_pr", ["project_id"])
    _create_index_safe(inspector, "ix_supplier_catalogs_pr_status", "oe_supplier_catalogs_pr", ["status"])
    _create_index_safe(inspector, "ix_supplier_catalogs_pr_line_pr", "oe_supplier_catalogs_pr_line", ["pr_id"])
    _create_index_safe(inspector, "ix_supplier_catalogs_po_number", "oe_supplier_catalogs_po", ["number"])
    _create_index_safe(inspector, "ix_supplier_catalogs_po_vendor", "oe_supplier_catalogs_po", ["vendor_id"])
    _create_index_safe(inspector, "ix_supplier_catalogs_po_project", "oe_supplier_catalogs_po", ["project_id"])
    _create_index_safe(inspector, "ix_supplier_catalogs_po_status", "oe_supplier_catalogs_po", ["status"])
    _create_index_safe(inspector, "ix_supplier_catalogs_po_line_po", "oe_supplier_catalogs_po_line", ["po_id"])
    _create_index_safe(inspector, "ix_supplier_catalogs_gr_po", "oe_supplier_catalogs_gr", ["po_id"])
    _create_index_safe(inspector, "ix_supplier_catalogs_gr_warehouse", "oe_supplier_catalogs_gr", ["warehouse_id"])
    _create_index_safe(inspector, "ix_supplier_catalogs_invoice_number", "oe_supplier_catalogs_invoice", ["number"])
    _create_index_safe(inspector, "ix_supplier_catalogs_invoice_vendor", "oe_supplier_catalogs_invoice", ["vendor_id"])
    _create_index_safe(inspector, "ix_supplier_catalogs_invoice_status", "oe_supplier_catalogs_invoice", ["status"])
    _create_index_safe(
        inspector, "ix_supplier_catalogs_match_invoice", "oe_supplier_catalogs_match_record", ["invoice_id"]
    )
    _create_index_safe(
        inspector, "ix_supplier_catalogs_balance_wh", "oe_supplier_catalogs_stock_balance", ["warehouse_id"]
    )
    _create_index_safe(
        inspector, "ix_supplier_catalogs_balance_item", "oe_supplier_catalogs_stock_balance", ["catalog_item_id"]
    )
    _create_index_safe(
        inspector, "ix_supplier_catalogs_movement_wh", "oe_supplier_catalogs_stock_movement", ["warehouse_id"]
    )
    _create_index_safe(
        inspector, "ix_supplier_catalogs_movement_type", "oe_supplier_catalogs_stock_movement", ["movement_type"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Drop in reverse dependency order. CASCADE lets PostgreSQL also remove
    # inbound FK constraints from sibling tables (e.g. the goods-receipt table
    # references the warehouse table), which otherwise block a plain DROP TABLE
    # with DependentObjectsStillExist.
    for tbl in reversed(_TABLES):
        if _has_table(inspector, tbl):
            op.execute(f'DROP TABLE IF EXISTS "{tbl}" CASCADE')
