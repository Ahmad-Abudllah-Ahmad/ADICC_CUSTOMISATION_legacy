# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Correspondence lifecycle + response deadline - status, response_required_by, contract_clause_ref.

Adds three additive columns to ``oe_correspondence_correspondence``:

* ``status`` (String(30), NOT NULL, server_default ``open``) - one of
  open|awaiting_response|responded|closed. Existing rows backfill to ``open``.
* ``response_required_by`` (String(20), nullable) - an ISO date (yyyy-mm-dd)
  by which a reply is contractually due.
* ``contract_clause_ref`` (String(120), nullable) - a free-text pointer to the
  contract clause a notice is served under (for example "NEC cl. 61.3").

The register was pure CRUD, so it could not track a formal notice with a legal
deadline: nothing distinguished an open notice from a closed one, and nothing
flagged one whose reply window had lapsed. These columns let the API compute an
overdue flag and a days-until-due countdown from the stored status and deadline.

Strictly additive and PostgreSQL-only. ``status`` carries a server default so
the NOT NULL add succeeds against a table that already holds rows; the other
two columns are nullable so no data rewrite is needed and existing records read
exactly as before.

This migration MUST be RUN (``alembic upgrade``), not merely stamped: prod
builds the schema with ``create_all`` + ``alembic stamp <head>``, and
create_all never adds columns to an already-existing table, so a stamp-only
deploy would leave the columns missing. The embedded-PostgreSQL runtime also
heals them via ``postgres_auto_migrate`` on boot.

Idempotent - inspector-guarded so a re-run on a partially-migrated DB (or a DB
the embedded-PostgreSQL runtime already auto-created via ``create_all``) skips
already-present columns. Chained after v3246_transmittal_recipient_identity to
keep a single linear head.

Revision ID: v3247_correspondence_status_deadline
Revises: v3246_transmittal_recipient_identity
Create Date: 2026-07-17
"""

from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3247_correspondence_status_deadline"
down_revision: Union[str, Sequence[str], None] = "v3246_transmittal_recipient_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Hardened identifier allow-list (mirrors the sibling migrations).
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


_TABLE = _safe_ident("oe_correspondence_correspondence")
_COL_STATUS = _safe_ident("status")
_COL_DUE = _safe_ident("response_required_by")
_COL_CLAUSE = _safe_ident("contract_clause_ref")


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _has_column(inspector: sa.engine.reflection.Inspector, table: str, column: str) -> bool:
    if not _has_table(inspector, table):
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    """Add ``status`` + ``response_required_by`` + ``contract_clause_ref`` (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, _TABLE) and not _has_column(inspector, _TABLE, _COL_STATUS):
        op.add_column(
            _TABLE,
            sa.Column(
                _COL_STATUS,
                sa.String(length=30),
                nullable=False,
                server_default="open",
            ),
        )
        op.create_index(
            op.f(f"ix_{_TABLE}_{_COL_STATUS}"),
            _TABLE,
            [_COL_STATUS],
            unique=False,
        )
    if _has_table(inspector, _TABLE) and not _has_column(inspector, _TABLE, _COL_DUE):
        op.add_column(_TABLE, sa.Column(_COL_DUE, sa.String(length=20), nullable=True))
    if _has_table(inspector, _TABLE) and not _has_column(inspector, _TABLE, _COL_CLAUSE):
        op.add_column(_TABLE, sa.Column(_COL_CLAUSE, sa.String(length=120), nullable=True))


def downgrade() -> None:
    """Drop the three columns (batch mode for SQLite compatibility, idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, _TABLE, _COL_CLAUSE):
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.drop_column(_COL_CLAUSE)
    if _has_column(inspector, _TABLE, _COL_DUE):
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.drop_column(_COL_DUE)
    if _has_column(inspector, _TABLE, _COL_STATUS):
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.drop_index(op.f(f"ix_{_TABLE}_{_COL_STATUS}"))
            batch_op.drop_column(_COL_STATUS)
