# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Quantity link - per-element formula projection (Issue #347).

Adds two columns to ``oe_boq_quantity_link``:

* ``projection_mode`` (String(16), server_default 'field') - 'field' reads a
  quantity key off each bound element (the original behaviour); 'formula'
  evaluates a per-element arithmetic expression then aggregates.
* ``formula`` (Text, nullable) - the expression used in 'formula' mode.

Strictly additive. ``projection_mode`` carries a server_default so existing
rows read as 'field' with no data rewrite; ``quantity_field`` is deliberately
left NOT NULL (formula-mode links store an empty string there) so nothing
existing is altered. Chained after ``v3236_boq_cad_model_id`` to keep a single
linear tip.

This migration MUST be RUN (``alembic upgrade``), not merely stamped: prod
builds the schema with ``create_all`` + ``alembic stamp <head>``, and
create_all never adds columns to an already-existing table, so a stamp-only
deploy would leave the columns missing.

Idempotent - inspector-guarded so a re-run on a partially-migrated DB skips
already-present columns.

Revision ID: v3237_quantity_link_formula
Revises: v3236_boq_cad_model_id
Create Date: 2026-07-13
"""

from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3237_quantity_link_formula"
down_revision: Union[str, Sequence[str], None] = "v3236_boq_cad_model_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Hardened identifier allow-list (mirrors the sibling migrations).
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


_TABLE = _safe_ident("oe_boq_quantity_link")
_COL_MODE = _safe_ident("projection_mode")
_COL_FORMULA = _safe_ident("formula")


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _has_column(inspector: sa.engine.reflection.Inspector, table: str, column: str) -> bool:
    if not _has_table(inspector, table):
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    """Add ``projection_mode`` + ``formula`` (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_table(inspector, _TABLE):
        # Parent migration hasn't run yet - nothing to upgrade. Degrade
        # silently so a re-run after a manual fix stays non-destructive.
        return

    if not _has_column(inspector, _TABLE, _COL_MODE):
        op.add_column(
            _TABLE,
            sa.Column(_COL_MODE, sa.String(length=16), nullable=True, server_default="field"),
        )
    if not _has_column(inspector, _TABLE, _COL_FORMULA):
        op.add_column(
            _TABLE,
            sa.Column(_COL_FORMULA, sa.Text(), nullable=True),
        )


def downgrade() -> None:
    """Drop both columns (batch mode for SQLite compatibility)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, _TABLE, _COL_FORMULA) or _has_column(inspector, _TABLE, _COL_MODE):
        with op.batch_alter_table(_TABLE) as batch_op:
            if _has_column(inspector, _TABLE, _COL_FORMULA):
                batch_op.drop_column(_COL_FORMULA)
            if _has_column(inspector, _TABLE, _COL_MODE):
                batch_op.drop_column(_COL_MODE)
