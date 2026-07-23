# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Takeoff document - source_document_id bridge (Project Files -> takeoff).

Adds one column to ``oe_takeoff_document``:

* ``source_document_id`` (String(36), nullable) - the originating
  ``oe_documents_document`` id when a takeoff document is created by opening a
  file from the Documents hub. NULL for direct uploads. It is the idempotency
  key for ``POST /documents/from-source/{id}`` so opening the same Project-Files
  PDF twice reuses one takeoff row instead of minting a duplicate and
  re-parsing.

Plus the matching index ``ix_oe_takeoff_document_source_document_id`` for the
once-per-open lookup (the same name SQLAlchemy's ``index=True`` emits, so
create_all and this migration never produce a duplicate index).

Strictly additive and nullable, so every existing row reads unchanged and no
backfill is needed. Chained after ``v3237_quantity_link_formula`` to keep a
single linear tip.

On normal deploys the column and index also ride ``create_all`` +
``postgres_auto_migrate``; this migration mainly keeps the revision graph and
any external/migration-driven DB consistent.

Idempotent - inspector-guarded so a re-run on a partially-migrated DB skips the
already-present column/index.

Revision ID: v3238_takeoff_source_document_id
Revises: v3237_quantity_link_formula
Create Date: 2026-07-13
"""

from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3238_takeoff_source_document_id"
down_revision: Union[str, Sequence[str], None] = "v3237_quantity_link_formula"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Hardened identifier allow-list (mirrors the sibling migrations).
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


_TABLE = _safe_ident("oe_takeoff_document")
_COL = _safe_ident("source_document_id")
_INDEX = _safe_ident("ix_oe_takeoff_document_source_document_id")


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _has_column(inspector: sa.engine.reflection.Inspector, table: str, column: str) -> bool:
    if not _has_table(inspector, table):
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def _has_index(inspector: sa.engine.reflection.Inspector, table: str, index: str) -> bool:
    if not _has_table(inspector, table):
        return False
    return any(i["name"] == index for i in inspector.get_indexes(table))


def upgrade() -> None:
    """Add ``source_document_id`` + its index (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_table(inspector, _TABLE):
        # Base table not created yet - nothing to alter. Degrade silently so a
        # re-run after a manual fix stays non-destructive.
        return

    if not _has_column(inspector, _TABLE, _COL):
        op.add_column(
            _TABLE,
            sa.Column(_COL, sa.String(length=36), nullable=True),
        )
    if not _has_index(inspector, _TABLE, _INDEX):
        op.create_index(_INDEX, _TABLE, [_COL])


def downgrade() -> None:
    """Drop the index + column (batch mode for cross-dialect safety)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_index(inspector, _TABLE, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)
    if _has_column(inspector, _TABLE, _COL):
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.drop_column(_COL)
