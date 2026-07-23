# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""BOQ position - owning BIM model of the linked elements.

Adds a single nullable ``cad_model_id`` column to ``oe_boq_position``. A
position's ``cad_element_ids`` list alone is ambiguous in a multi-model
project: a stable_id is unique only per model, and even a DB-UUID element id
must be resolved against the right model's element set. Recording the owning
model lets the BOQ "pick quantity from BIM" picker and the mini 3D preview
resolve each position against ITS model instead of the project's first-ready
one.

Strictly additive - no existing column is touched. The column is nullable so
legacy rows keep working (callers fall back to the project-level model, the
pre-change behaviour, which is correct for single-model projects).

upgrade() best-effort back-fills the new column from the canonical link table
``oe_bim_boq_link`` joined to ``oe_bim_element`` (one owning model per
position). The back-fill is wrapped so a schema where those tables are absent
or empty never blocks the column add.

Idempotent - inspector-guarded so a re-run on a partially-migrated DB skips
the already-present column. Chained after ``v3235_design_options`` so the
alembic graph keeps a single linear tip.

Revision ID: v3236_boq_cad_model_id
Revises: v3235_design_options
Create Date: 2026-07-13
"""

from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3236_boq_cad_model_id"
down_revision: Union[str, Sequence[str], None] = "v3235_design_options"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Hardened identifier allow-list (mirrors the sibling migrations). Every
# identifier interpolated into raw SQL must pass ``_safe_ident`` so a future
# edit cannot grow the fragile-f-string pattern into an injection vector.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    """Return ``name`` unchanged if it's a valid SQL identifier, else raise."""
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


_TABLE = _safe_ident("oe_boq_position")
_COLUMN = _safe_ident("cad_model_id")
_LINK_TABLE = _safe_ident("oe_bim_boq_link")
_ELEM_TABLE = _safe_ident("oe_bim_element")


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _has_column(inspector: sa.engine.reflection.Inspector, table: str, column: str) -> bool:
    if not _has_table(inspector, table):
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def _backfill(bind: sa.engine.Connection, inspector: sa.engine.reflection.Inspector) -> None:
    """Best-effort: set ``cad_model_id`` from the canonical link table.

    Joins ``oe_bim_boq_link`` -> ``oe_bim_element`` and takes one owning model
    per position (``MIN`` on the 36-char model-id string - deterministic).
    Only fills rows that are still NULL. Silent no-op when the source tables
    are missing or the statement fails, so the column add is never blocked.
    """
    if not (
        _has_table(inspector, _LINK_TABLE)
        and _has_table(inspector, _ELEM_TABLE)
        and _has_column(inspector, _TABLE, _COLUMN)
    ):
        return

    dialect = bind.dialect.name
    try:
        if dialect == "postgresql":
            bind.execute(
                sa.text(
                    "UPDATE oe_boq_position AS p "
                    "SET cad_model_id = sub.model_id "
                    "FROM ("
                    "  SELECT l.boq_position_id AS pos_id, MIN(e.model_id) AS model_id "
                    "  FROM oe_bim_boq_link l "
                    "  JOIN oe_bim_element e ON e.id = l.bim_element_id "
                    "  GROUP BY l.boq_position_id"
                    ") AS sub "
                    "WHERE p.id = sub.pos_id AND p.cad_model_id IS NULL"
                )
            )
        else:
            # SQLite (and any other dialect) - correlated subquery form.
            bind.execute(
                sa.text(
                    "UPDATE oe_boq_position "
                    "SET cad_model_id = ("
                    "  SELECT MIN(e.model_id) FROM oe_bim_boq_link l "
                    "  JOIN oe_bim_element e ON e.id = l.bim_element_id "
                    "  WHERE l.boq_position_id = oe_boq_position.id"
                    ") "
                    "WHERE cad_model_id IS NULL AND EXISTS ("
                    "  SELECT 1 FROM oe_bim_boq_link l "
                    "  WHERE l.boq_position_id = oe_boq_position.id"
                    ")"
                )
            )
    except sa.exc.SQLAlchemyError:
        # Back-fill is a convenience, not a correctness requirement - the live
        # write paths populate cad_model_id going forward and NULL rows fall
        # back to the project-level model. Never fail the migration over it.
        pass


def upgrade() -> None:
    """Add ``cad_model_id`` (idempotent) and best-effort back-fill it."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_table(inspector, _TABLE):
        # Parent migration hasn't run yet - nothing to upgrade. Degrade
        # silently so a re-run after a manual fix stays non-destructive.
        return

    if not _has_column(inspector, _TABLE, _COLUMN):
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.String(length=36), nullable=True),
        )
        # Re-inspect so the back-fill sees the freshly-added column.
        inspector = sa.inspect(bind)

    _backfill(bind, inspector)


def downgrade() -> None:
    """Drop the column (batch mode for SQLite compatibility)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, _TABLE, _COLUMN):
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.drop_column(_COLUMN)
