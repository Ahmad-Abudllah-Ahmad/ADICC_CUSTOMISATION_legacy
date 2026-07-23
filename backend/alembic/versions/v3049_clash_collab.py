# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Clash — Wave A3 collaboration columns.

Additive, all backward-compatible columns on ``oe_clash_result`` so the
Wave A3 collaboration features (BCF round-trip, watchers, audit log)
can persist their state without breaking any existing payload:

* ``watchers`` — NOT NULL JSON default ``[]``. List of user-id strings
                 subscribed to this clash for notification fan-out.
* ``history``  — NOT NULL JSON default ``[]``. Audit trail of
                 ``{ts, actor, field, before, after}`` entries appended
                 on every triage mutation (status / severity / assignee
                 / due_date) and every new comment. Chronological order.

Idempotent: inspector-guarded so re-running after SQLite's
``Base.metadata.create_all`` / ``sqlite_auto_migrate`` (dev) is a no-op;
Postgres prod gets the DDL. Mirrors v3047_clash_severity_delta exactly.

Revision ID: v3049_clash_collab
Revises: v3048_clash_a2_metadata
Created: 2026-05-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3049_clash_collab"
down_revision: Union[str, Sequence[str], None] = "v3048_clash_a2_metadata"
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
    if "watchers" not in cols:
        op.add_column(
            _RESULT,
            sa.Column(
                "watchers",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            ),
        )
    if "history" not in cols:
        op.add_column(
            _RESULT,
            sa.Column(
                "history",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, _RESULT):
        return
    cols = {c["name"] for c in inspector.get_columns(_RESULT)}
    if "history" in cols:
        op.drop_column(_RESULT, "history")
    if "watchers" in cols:
        op.drop_column(_RESULT, "watchers")
