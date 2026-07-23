"""Migrate CostModel data (CostSnapshot, BudgetLine) into Finance module tables.

Reads from the legacy ``oe_costmodel_snapshot`` and ``oe_costmodel_budget_line``
tables and creates corresponding ``oe_finance_evm_snapshot`` and
``oe_finance_budget`` records.

The script is **idempotent** — duplicate records (matched by project_id +
period / project_id + category) are silently skipped.

Run::

    cd backend
    python -m scripts.migrate_costmodel_to_finance
"""

from __future__ import annotations

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


def run() -> None:
    """Execute the CostModel -> Finance data migration."""
    url = _get_sync_url()
    engine = sa.create_engine(url)

    with engine.begin() as conn:
        # --- Pre-flight checks ------------------------------------------------
        if not _table_exists(conn, "oe_costmodel_snapshot"):
            logger.info("Source table oe_costmodel_snapshot does not exist — nothing to migrate.")
            return
        if not _table_exists(conn, "oe_finance_evm_snapshot"):
            logger.warning("Target table oe_finance_evm_snapshot does not exist. Run alembic upgrade head first.")
            return

        # --- Migrate CostSnapshot -> EVMSnapshot ------------------------------
        snapshots_migrated = 0
        snapshots_skipped = 0

        rows = conn.execute(sa.text("SELECT * FROM oe_costmodel_snapshot")).mappings().all()

        for row in rows:
            project_id = str(row["project_id"])
            period = row["period"]  # "YYYY-MM" — used as snapshot_date

            # Deduplicate: skip if an EVM snapshot already exists for this project+period
            existing = conn.execute(
                sa.text("SELECT id FROM oe_finance_evm_snapshot WHERE project_id = :pid AND snapshot_date = :sd"),
                {"pid": project_id, "sd": period},
            ).first()
            if existing is not None:
                snapshots_skipped += 1
                continue

            new_id = str(uuid.uuid4())
            conn.execute(
                sa.text(
                    "INSERT INTO oe_finance_evm_snapshot "
                    "(id, project_id, snapshot_date, bac, pv, ev, ac, sv, cv, spi, cpi, metadata, "
                    " created_at, updated_at) "
                    "VALUES (:id, :pid, :sd, :bac, :pv, :ev, :ac, :sv, :cv, :spi, :cpi, :meta, "
                    " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": new_id,
                    "pid": project_id,
                    "sd": period,
                    "bac": row.get("forecast_eac", "0"),
                    "pv": row.get("planned_cost", "0"),
                    "ev": row.get("earned_value", "0"),
                    "ac": row.get("actual_cost", "0"),
                    "sv": "0",  # Not directly available in CostSnapshot
                    "cv": "0",
                    "spi": row.get("spi", "0"),
                    "cpi": row.get("cpi", "0"),
                    "meta": '{"migrated_from": "oe_costmodel_snapshot"}',
                },
            )
            snapshots_migrated += 1

        # --- Migrate BudgetLine -> ProjectBudget ------------------------------
        budgets_migrated = 0
        budgets_skipped = 0

        if not _table_exists(conn, "oe_costmodel_budget_line"):
            logger.info("Source table oe_costmodel_budget_line does not exist — skipping budgets.")
        elif not _table_exists(conn, "oe_finance_budget"):
            logger.warning("Target table oe_finance_budget does not exist. Run alembic upgrade head first.")
        else:
            budget_rows = conn.execute(sa.text("SELECT * FROM oe_costmodel_budget_line")).mappings().all()

            for brow in budget_rows:
                project_id = str(brow["project_id"])
                category = brow.get("category", "")

                # Deduplicate: match on project_id + wbs_id(NULL) + category
                existing = conn.execute(
                    sa.text(
                        "SELECT id FROM oe_finance_budget "
                        "WHERE project_id = :pid AND category = :cat AND wbs_id IS NULL"
                    ),
                    {"pid": project_id, "cat": category},
                ).first()
                if existing is not None:
                    budgets_skipped += 1
                    continue

                new_id = str(uuid.uuid4())
                conn.execute(
                    sa.text(
                        "INSERT INTO oe_finance_budget "
                        "(id, project_id, wbs_id, category, original_budget, revised_budget, "
                        " committed, actual, forecast_final, metadata, "
                        " created_at, updated_at) "
                        "VALUES (:id, :pid, NULL, :cat, :orig, :revised, "
                        " :committed, :actual, :forecast, :meta, "
                        " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {
                        "id": new_id,
                        "pid": project_id,
                        "cat": category,
                        "orig": brow.get("planned_amount", "0"),
                        "revised": brow.get("planned_amount", "0"),
                        "committed": brow.get("committed_amount", "0"),
                        "actual": brow.get("actual_amount", "0"),
                        "forecast": brow.get("forecast_amount", "0"),
                        "meta": '{"migrated_from": "oe_costmodel_budget_line"}',
                    },
                )
                budgets_migrated += 1

    logger.info(
        "Migration complete: %d snapshots migrated (%d skipped), %d budget lines migrated (%d skipped).",
        snapshots_migrated,
        snapshots_skipped,
        budgets_migrated,
        budgets_skipped,
    )


if __name__ == "__main__":
    try:
        run()
    except Exception:
        logger.exception("Migration failed")
        sys.exit(1)
