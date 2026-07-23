# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Ledger idempotency - guard against GL double-posting and double-reversal.

Two money-correctness fixes share the ``oe_finance_ledger`` table, so they ship
in one step:

    * Journal/transaction posting was not idempotent - a retried post inserted a
      second set of ledger rows and double-counted the general ledger.
    * Reversal was not idempotent - reversing the same transaction twice wrote a
      second corrective pair and over-corrected the account.

Both are now keyed by a shared, deterministic ``idempotency_key`` (one key per
posting / per reversal, the same on every leg). The service existence-checks the
key before writing and returns the existing rows on a replay. This migration
adds the DB-level backstop:

    oe_finance_ledger.idempotency_key  - nullable String(64). NULL on legacy
        rows and on any write that opts out.
    uq_finance_ledger_idempotency      - partial UNIQUE index on
        (idempotency_key, account_code) WHERE idempotency_key IS NOT NULL, so
        a concurrent duplicate write is rejected while legacy NULL rows never
        collide. account_code is in the key so the distinct-account legs of one
        posting coexist while a full replay still collides.

The embedded PostgreSQL runtime materialises the column and the partial index
via ``create_all`` at startup, so this migration is for external PostgreSQL
deployments that manage schema with Alembic. Every step is presence-guarded so a
re-run, or a DB the runtime already auto-created, is a no-op. Additive and
backfill-safe: existing rows keep a NULL key and are excluded by the partial
predicate, so no dedupe pass is required. PostgreSQL-only, no SQLite shims.

Revision ID: v3183_finance_ledger_idempotency
Revises: v3182_boq_position_copilot
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3183_finance_ledger_idempotency"
down_revision = "v3182_boq_position_copilot"
branch_labels = None
depends_on = None

_TABLE = "oe_finance_ledger"
_COLUMN = "idempotency_key"
_INDEX = "uq_finance_ledger_idempotency"


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def _has_index(table: str, name: str) -> bool:
    if not _has_table(table):
        return False
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if not _has_column(_TABLE, _COLUMN):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(64), nullable=True))
        # Plain (non-unique) lookup index mirrors the model's index=True so the
        # service existence-check stays cheap.
        op.create_index("ix_oe_finance_ledger_idempotency_key", _TABLE, [_COLUMN])

    # Partial unique backstop. WHERE idempotency_key IS NOT NULL keeps legacy
    # NULL rows out of the constraint so they never collide with each other.
    if _has_table(_TABLE) and not _has_index(_TABLE, _INDEX):
        op.create_index(
            _INDEX,
            _TABLE,
            [_COLUMN, "account_code"],
            unique=True,
            sqlite_where=sa.text("idempotency_key IS NOT NULL"),
            postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        )


def downgrade() -> None:
    if _has_index(_TABLE, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)
    if _has_index(_TABLE, "ix_oe_finance_ledger_idempotency_key"):
        op.drop_index("ix_oe_finance_ledger_idempotency_key", table_name=_TABLE)
    if _has_column(_TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
