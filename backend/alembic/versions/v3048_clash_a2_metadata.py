# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Clash Wave A2 — engine-derived advisory metadata envelope.

Adds a single open-ended JSON column to ``oe_clash_result``:

* ``meta`` — NOT NULL JSON default ``'{}'``. Open-ended envelope for
             engine-derived annotations that are *not* authoritative state
             (the user-confirmed ``severity``/``status``/``assigned_to``
             columns remain the source of truth). Wave A2 seeds it with
             ``{"severity_suggestion": "<one-step-up>"}`` on deep hard
             clashes (``penetration_m > 0.10``); the UI surfaces a
             "Suggested: …" chip the user can act on. SQLAlchemy reserves
             ``metadata`` on Base, so the column is mapped as ``meta``.

Idempotent: inspector-guarded so re-running after SQLite's
``Base.metadata.create_all`` / ``sqlite_auto_migrate`` (dev) is a no-op;
Postgres prod gets the DDL.

Revision ID: v3048_clash_a2_metadata
Revises: v3047_clash_severity_delta
Created: 2026-05-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3048_clash_a2_metadata"
down_revision: Union[str, Sequence[str], None] = "v3047_clash_severity_delta"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RESULT = "oe_clash_result"


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, _RESULT):
        return
    cols = {c["name"] for c in inspector.get_columns(_RESULT)}
    if "meta" not in cols:
        op.add_column(
            _RESULT,
            sa.Column(
                "meta",
                sa.JSON(),
                nullable=False,
                server_default="{}",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, _RESULT):
        return
    cols = {c["name"] for c in inspector.get_columns(_RESULT)}
    if "meta" in cols:
        op.drop_column(_RESULT, "meta")
