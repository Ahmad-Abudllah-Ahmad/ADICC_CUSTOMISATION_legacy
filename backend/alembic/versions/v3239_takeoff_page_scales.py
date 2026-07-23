# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Takeoff document - page_scales column (per-page drawing scale map).

Adds one column to ``oe_takeoff_document``:

* ``page_scales`` (JSON, nullable) - the per-page drawing-scale map stamped at
  the document level, so every measurement on a page inherits one scale (falling
  back to the legacy per-measurement stamps when absent). NULL for documents
  that carry no document-level scale, so every existing row reads unchanged and
  no backfill is needed.

Strictly additive and nullable. Chained after
``v3238_takeoff_source_document_id`` to keep a single linear tip.

On normal deploys the column also rides ``create_all`` +
``postgres_auto_migrate``; this migration mainly keeps the revision graph and
any external / DDL-restricted DB consistent, since those never run create_all
and so would otherwise never get the column.

Idempotent - inspector-guarded so a re-run on a partially-migrated DB skips the
already-present column.

Revision ID: v3239_takeoff_page_scales
Revises: v3238_takeoff_source_document_id
Create Date: 2026-07-13
"""

from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3239_takeoff_page_scales"
down_revision: Union[str, Sequence[str], None] = "v3238_takeoff_source_document_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Hardened identifier allow-list (mirrors the sibling migrations).
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


_TABLE = _safe_ident("oe_takeoff_document")
_COL = _safe_ident("page_scales")


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _has_column(inspector: sa.engine.reflection.Inspector, table: str, column: str) -> bool:
    if not _has_table(inspector, table):
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    """Add ``page_scales`` (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_table(inspector, _TABLE):
        # Base table not created yet - nothing to alter. Degrade silently so a
        # re-run after a manual fix stays non-destructive.
        return

    if not _has_column(inspector, _TABLE, _COL):
        op.add_column(
            _TABLE,
            sa.Column(_COL, sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    """Drop the column (batch mode for cross-dialect safety)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, _TABLE, _COL):
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.drop_column(_COL)
