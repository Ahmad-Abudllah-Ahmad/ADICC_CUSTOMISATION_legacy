# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""markups_measurement_numeric — Float → NUMERIC(18,6) on calibration / measurement.

Round 3 Wave A flagged ``markups/models.py:42,72,77`` (``measurement_value``,
``pixels_per_unit``, ``real_distance``) as ``Float``. These columns feed BOQ
quantities and PDF-page calibration — both demand DECIMAL precision so that:

* a 12.345678 m calibrated distance round-trips identically (no binary
  float drift that would shift every length measurement off the drawing),
* a measurement aggregated into a BOQ position lines up with the
  platform money-numeric convention (scale=6, see Phase 2e migration
  ``7f3ab0f2d4e1_phase2e_money_numeric``).

Also merges the two outstanding 3096 heads
(``v3096_round3_fk_indexes`` + ``v3096_regional_indices_certainty``) so
the head is single again.

SQLite is intentionally skipped for the column-type rewrite — SQLite
stores everything as text regardless of declared type, the SQLAlchemy
``Numeric`` decorator handles Python-side ``Decimal`` normalisation, and a
``batch_alter_table`` rebuild would churn every row for zero storage
benefit. Dev DBs keep working against the new ORM definitions unchanged.

Revision ID: v3097_markups_measurement_numeric
Revises: v3096, v3096_regional_indices_certainty
Create Date: 2026-05-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3097_markups_measurement_numeric"
down_revision: Union[str, Sequence[str], None] = (
    "v3096",
    "v3096_regional_indices_certainty",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column) pairs to rewrite as NUMERIC(18,6).
_MEASUREMENT_COLUMNS: list[tuple[str, str]] = [
    ("oe_markups_markup", "measurement_value"),
    ("oe_markups_scale_config", "pixels_per_unit"),
    ("oe_markups_scale_config", "real_distance"),
]


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    """Switch markup calibration/measurement columns to NUMERIC(18, 6)."""
    if not _is_postgres():
        # SQLite / other: no-op (typeless storage, ORM ``Numeric`` handles it).
        return

    for table, column in _MEASUREMENT_COLUMNS:
        # ``USING`` clause lets Postgres cast the existing DOUBLE PRECISION
        # row by row. ``NULLIF`` guards against empty-string sentinels that
        # could only ever appear if a stray text-typed import slipped past.
        op.execute(
            sa.text(
                f"""
                ALTER TABLE {table}
                ALTER COLUMN {column} TYPE NUMERIC(18, 6)
                USING NULLIF({column}::text, '')::numeric
                """,
            ),
        )


def downgrade() -> None:
    """Roll columns back to DOUBLE PRECISION."""
    if not _is_postgres():
        return

    for table, column in _MEASUREMENT_COLUMNS:
        op.execute(
            sa.text(
                f"""
                ALTER TABLE {table}
                ALTER COLUMN {column} TYPE DOUBLE PRECISION
                USING {column}::double precision
                """,
            ),
        )
