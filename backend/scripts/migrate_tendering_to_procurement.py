"""Migrate Tendering data (TenderPackage, TenderBid) into Procurement module tables.

For each ``TenderPackage`` with an awarded bid, creates a corresponding
``PurchaseOrder`` in ``oe_procurement_po``.  Bid details are stored as
metadata on the PO for traceability.

The script is **idempotent** — packages that already have a linked PO
(detected via metadata ``tender_package_id``) are silently skipped.

Run::

    cd backend
    python -m scripts.migrate_tendering_to_procurement
"""

from __future__ import annotations

import json
import logging
import sys
import uuid

import sqlalchemy as sa

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _table_exists(conn: sa.engine.Connection, table_name: str) -> bool:
    """Return True if *table_name* exists in the current database."""
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def _get_sync_url() -> str:
    """Resolve the synchronous DB URL from app settings or fallback."""
    try:
        from app.config import get_settings

        return get_settings().database_sync_url
    except Exception:
        return "sqlite:///./openestimate.db"


def _next_po_number(conn: sa.engine.Connection) -> str:
    """Generate the next PO number based on existing records."""
    result = conn.execute(sa.text("SELECT COUNT(*) FROM oe_procurement_po")).scalar()
    return f"PO-{(result or 0) + 1:06d}"


def run() -> None:
    """Execute the Tendering -> Procurement data migration."""
    url = _get_sync_url()
    engine = sa.create_engine(url)

    with engine.begin() as conn:
        # --- Pre-flight checks ------------------------------------------------
        if not _table_exists(conn, "oe_tendering_package"):
            logger.info("Source table oe_tendering_package does not exist — nothing to migrate.")
            return
        if not _table_exists(conn, "oe_procurement_po"):
            logger.warning("Target table oe_procurement_po does not exist. Run alembic upgrade head first.")
            return

        # --- Load all tender packages -----------------------------------------
        packages = conn.execute(sa.text("SELECT * FROM oe_tendering_package")).mappings().all()

        if not packages:
            logger.info("No tender packages found — nothing to migrate.")
            return

        bids_table_exists = _table_exists(conn, "oe_tendering_bid")

        pos_created = 0
        pos_skipped = 0

        for pkg in packages:
            pkg_id = str(pkg["id"])
            project_id = str(pkg["project_id"])

            # --- Check for awarded bids ---------------------------------------
            awarded_bid = None
            all_bids: list[dict] = []
            if bids_table_exists:
                bid_rows = (
                    conn.execute(
                        sa.text("SELECT * FROM oe_tendering_bid WHERE package_id = :pid ORDER BY total_amount ASC"),
                        {"pid": pkg_id},
                    )
                    .mappings()
                    .all()
                )
                all_bids = [dict(b) for b in bid_rows]

                # Find the awarded bid (status == 'awarded') or skip
                for b in all_bids:
                    if b.get("status") == "awarded":
                        awarded_bid = b
                        break

            if awarded_bid is None:
                # Only migrate packages that have an awarded bid
                pos_skipped += 1
                continue

            # --- Deduplicate: check if PO already exists for this package -----
            # We look for metadata containing tender_package_id
            existing = conn.execute(
                sa.text("SELECT id FROM oe_procurement_po WHERE metadata LIKE :pattern"),
                {"pattern": f'%"tender_package_id": "{pkg_id}"%'},
            ).first()
            if existing is not None:
                pos_skipped += 1
                continue

            # --- Create PurchaseOrder -----------------------------------------
            po_id = str(uuid.uuid4())
            po_number = _next_po_number(conn)

            # Build metadata with full traceability
            po_metadata = {
                "migrated_from": "oe_tendering_package",
                "tender_package_id": pkg_id,
                "tender_package_name": pkg.get("name", ""),
                "awarded_bid_id": str(awarded_bid.get("id", "")),
                "awarded_company": awarded_bid.get("company_name", ""),
                "all_bids_count": len(all_bids),
                "all_bids_summary": [
                    {
                        "company": b.get("company_name", ""),
                        "amount": b.get("total_amount", "0"),
                        "status": b.get("status", ""),
                    }
                    for b in all_bids
                ],
            }

            conn.execute(
                sa.text(
                    "INSERT INTO oe_procurement_po "
                    "(id, project_id, vendor_contact_id, po_number, po_type, "
                    " issue_date, delivery_date, currency_code, "
                    " amount_subtotal, tax_amount, amount_total, "
                    " status, payment_terms, notes, created_by, metadata, "
                    " created_at, updated_at) "
                    "VALUES (:id, :pid, :vendor, :po_num, :po_type, "
                    " :issue, :delivery, :currency, "
                    " :subtotal, :tax, :total, "
                    " :status, :terms, :notes, :created_by, :meta, "
                    " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": po_id,
                    "pid": project_id,
                    "vendor": None,  # Contact ID not directly mapped
                    "po_num": po_number,
                    "po_type": "subcontract",
                    "issue": None,
                    "delivery": pkg.get("deadline"),
                    "currency": awarded_bid.get("currency", "EUR"),
                    "subtotal": awarded_bid.get("total_amount", "0"),
                    "tax": "0",
                    "total": awarded_bid.get("total_amount", "0"),
                    "status": "draft",
                    "terms": None,
                    "notes": (
                        f"Auto-created from tender package '{pkg.get('name', '')}'. "
                        f"Awarded to {awarded_bid.get('company_name', 'N/A')}."
                    ),
                    "created_by": None,
                    "meta": json.dumps(po_metadata),
                },
            )
            pos_created += 1

            # --- Create PO line items from awarded bid line_items (if any) ----
            bid_line_items = awarded_bid.get("line_items")
            if isinstance(bid_line_items, str):
                try:
                    bid_line_items = json.loads(bid_line_items)
                except (json.JSONDecodeError, TypeError):
                    bid_line_items = []
            if not isinstance(bid_line_items, list):
                bid_line_items = []

            if _table_exists(conn, "oe_procurement_po_item"):
                for idx, item in enumerate(bid_line_items):
                    item_id = str(uuid.uuid4())
                    conn.execute(
                        sa.text(
                            "INSERT INTO oe_procurement_po_item "
                            "(id, po_id, description, quantity, unit, unit_rate, amount, "
                            " wbs_id, cost_category, sort_order, created_at, updated_at) "
                            "VALUES (:id, :po_id, :desc, :qty, :unit, :rate, :amt, "
                            " :wbs, :cat, :sort, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                        ),
                        {
                            "id": item_id,
                            "po_id": po_id,
                            "desc": item.get("description", f"Line item {idx + 1}"),
                            "qty": str(item.get("quantity", "1")),
                            "unit": item.get("unit"),
                            "rate": str(item.get("unit_rate", "0")),
                            "amt": str(item.get("amount", "0")),
                            "wbs": item.get("wbs_id"),
                            "cat": item.get("cost_category"),
                            "sort": idx,
                        },
                    )

    logger.info(
        "Migration complete: %d purchase orders created, %d packages skipped.",
        pos_created,
        pos_skipped,
    )


if __name__ == "__main__":
    try:
        run()
    except Exception:
        logger.exception("Migration failed")
        sys.exit(1)
