# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Transmittal recipient free-text identity - recipient_name + recipient_email.

Adds two additive columns to ``oe_transmittals_recipient``:

* ``recipient_name`` (String(200), nullable) - a recipient named by free text.
* ``recipient_email`` (String(320), nullable) - their email address.

A transmittal is most often sent to an external party who is neither a system
user nor a stored contact, so the recipient table previously had nowhere to
record who a recipient actually was (only org/user UUIDs). The create form was
therefore dropping the typed recipients into the transmittal metadata and the
issue step, which requires at least one recipient, could never be satisfied
from the UI. These columns let a recipient carry a real name and email.

Strictly additive and PostgreSQL-only. Both columns are nullable so no data
rewrite is needed and existing recipients read exactly as before.

This migration MUST be RUN (``alembic upgrade``), not merely stamped: prod
builds the schema with ``create_all`` + ``alembic stamp <head>``, and
create_all never adds columns to an already-existing table, so a stamp-only
deploy would leave the columns missing. The embedded-PostgreSQL runtime also
heals them via ``postgres_auto_migrate`` on boot.

Idempotent - inspector-guarded so a re-run on a partially-migrated DB (or a DB
the embedded-PostgreSQL runtime already auto-created via ``create_all``) skips
already-present columns. Chained after v3245_assembly_parameters to keep a
single linear head.

Revision ID: v3246_transmittal_recipient_identity
Revises: v3245_assembly_parameters
Create Date: 2026-07-17
"""

from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3246_transmittal_recipient_identity"
down_revision: Union[str, Sequence[str], None] = "v3245_assembly_parameters"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Hardened identifier allow-list (mirrors the sibling migrations).
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


_RECIPIENT = _safe_ident("oe_transmittals_recipient")
_COL_NAME = _safe_ident("recipient_name")
_COL_EMAIL = _safe_ident("recipient_email")


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _has_column(inspector: sa.engine.reflection.Inspector, table: str, column: str) -> bool:
    if not _has_table(inspector, table):
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    """Add ``recipient_name`` + ``recipient_email`` (idempotent, additive)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, _RECIPIENT) and not _has_column(inspector, _RECIPIENT, _COL_NAME):
        op.add_column(_RECIPIENT, sa.Column(_COL_NAME, sa.String(length=200), nullable=True))
    if _has_table(inspector, _RECIPIENT) and not _has_column(inspector, _RECIPIENT, _COL_EMAIL):
        op.add_column(_RECIPIENT, sa.Column(_COL_EMAIL, sa.String(length=320), nullable=True))


def downgrade() -> None:
    """Drop both columns (batch mode for SQLite compatibility, idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, _RECIPIENT, _COL_EMAIL):
        with op.batch_alter_table(_RECIPIENT) as batch_op:
            batch_op.drop_column(_COL_EMAIL)
    if _has_column(inspector, _RECIPIENT, _COL_NAME):
        with op.batch_alter_table(_RECIPIENT) as batch_op:
            batch_op.drop_column(_COL_NAME)
