# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Parametric assemblies - assembly parameters + component quantity formula (#365).

Adds two additive columns:

* ``oe_assemblies_assembly.parameters`` (JSON, server_default '[]') - the
  ordered list of parameter definitions that drive the recipe. Existing rows
  read as an empty list, i.e. a plain non-parametric assembly.
* ``oe_assemblies_component.quantity_formula`` (Text, nullable) - the optional
  per-component quantity formula over those parameters. NULL keeps the static
  ``quantity`` (mirrors ``oe_boq_quantity_link.formula`` from #347).

Strictly additive and PostgreSQL-only. Both columns carry a safe default /
NULL so no data rewrite is needed and existing assemblies behave exactly as
before.

This migration MUST be RUN (``alembic upgrade``), not merely stamped: prod
builds the schema with ``create_all`` + ``alembic stamp <head>``, and
create_all never adds columns to an already-existing table, so a stamp-only
deploy would leave the columns missing.

Idempotent - inspector-guarded so a re-run on a partially-migrated DB (or a DB
the embedded-PostgreSQL runtime already auto-created via ``create_all``) skips
already-present columns. Chained after v3244_defects_liability to keep a
single linear head.

Revision ID: v3245_assembly_parameters
Revises: v3244_defects_liability
Create Date: 2026-07-17
"""

from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3245_assembly_parameters"
down_revision: Union[str, Sequence[str], None] = "v3244_defects_liability"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Hardened identifier allow-list (mirrors the sibling migrations).
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


_ASSEMBLY = _safe_ident("oe_assemblies_assembly")
_COMPONENT = _safe_ident("oe_assemblies_component")
_COL_PARAMETERS = _safe_ident("parameters")
_COL_QUANTITY_FORMULA = _safe_ident("quantity_formula")


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _has_column(inspector: sa.engine.reflection.Inspector, table: str, column: str) -> bool:
    if not _has_table(inspector, table):
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    """Add ``parameters`` + ``quantity_formula`` (idempotent, additive)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, _ASSEMBLY) and not _has_column(inspector, _ASSEMBLY, _COL_PARAMETERS):
        op.add_column(
            _ASSEMBLY,
            sa.Column(_COL_PARAMETERS, sa.JSON(), nullable=False, server_default="[]"),
        )
    if _has_table(inspector, _COMPONENT) and not _has_column(inspector, _COMPONENT, _COL_QUANTITY_FORMULA):
        op.add_column(
            _COMPONENT,
            sa.Column(_COL_QUANTITY_FORMULA, sa.Text(), nullable=True),
        )


def downgrade() -> None:
    """Drop both columns (batch mode for SQLite compatibility, idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, _COMPONENT, _COL_QUANTITY_FORMULA):
        with op.batch_alter_table(_COMPONENT) as batch_op:
            batch_op.drop_column(_COL_QUANTITY_FORMULA)
    if _has_column(inspector, _ASSEMBLY, _COL_PARAMETERS):
        with op.batch_alter_table(_ASSEMBLY) as batch_op:
            batch_op.drop_column(_COL_PARAMETERS)
