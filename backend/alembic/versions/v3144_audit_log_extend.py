# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""epic-H: extend ``oe_activity_log`` with universal-audit columns.

Adds 8 nullable columns to the existing ``oe_activity_log`` table so the
single audit row written by :func:`app.core.audit_log.log_activity`
captures everything needed for an ISO 19650 / SCL / FIDIC dispute
timeline without forcing every module to invent its own schema:

* ``ip_address``           — request peer IP (varchar 45 — fits IPv6).
* ``user_agent``           — request UA, truncated to 500 chars.
* ``request_id``           — correlation ID echoed back to the client.
* ``module``               — logical module ("rfi" / "submittals" / …)
                              for cross-module timeline filtering.
* ``parent_entity_type``   — optional umbrella entity (e.g. ``project``
                              for an RFI created under that project).
* ``parent_entity_id``     — UUID of the parent entity.
* ``before_state``         — JSON snapshot of the affected record's
                              prior column values (small subset chosen
                              by the writer, NOT the full row).
* ``after_state``          — JSON snapshot of the new column values.

Also creates a composite ``(entity_type, entity_id, created_at)`` index
so the per-entity timeline endpoint can answer "give me the last 50
events for this RFI" without a sort step on the heap.

Idempotent: every column / index existence check happens up-front so the
upgrade is safe to re-run, and Fresh installs that boot the app first
already have these columns via ``Base.metadata.create_all``.

SQLite note: composite indexes on SQLite ignore per-column ``DESC``
specifiers, so the index is declared in ascending order on every column.
PostgreSQL behaves the same when the query plan would still scan in
DESC.

Revision ID: v3144_audit_log_extend
Revises: v3141_ai_kimi_api_key
Create Date: 2026-05-26
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3144_audit_log_extend"
down_revision: Union[str, None] = "v3143_unified_file_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_TABLE = "oe_activity_log"
_INDEX_NAME = "ix_activity_log_entity_created"

# (column_name, sqlalchemy type, server_default) — all nullable on purpose.
# ``server_default=None`` (i.e. the column default is NULL) is made
# explicit by ``sa.null()`` rather than omitted; SQLAlchemy still emits
# the bare column without a DEFAULT clause when the value is ``None``.
_NEW_COLUMNS: tuple[tuple[str, sa.types.TypeEngine, sa.sql.elements.ColumnElement | None], ...] = (
    ("ip_address", sa.String(length=45), None),
    ("user_agent", sa.String(length=500), None),
    ("request_id", sa.String(length=64), None),
    ("module", sa.String(length=64), None),
    ("parent_entity_type", sa.String(length=64), None),
    ("parent_entity_id", sa.String(length=64), None),
    ("before_state", sa.JSON(), None),
    ("after_state", sa.JSON(), None),
)


def _column_exists(bind: sa.engine.Connection, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def _index_exists(bind: sa.engine.Connection, table: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(ix["name"] == index_name for ix in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        logger.info("v3144: %s missing — fresh DB will create_all on boot", _TABLE)
        return

    for col_name, col_type, server_default in _NEW_COLUMNS:
        if _column_exists(bind, _TABLE, col_name):
            continue
        kwargs: dict = {"nullable": True}
        if server_default is not None:
            kwargs["server_default"] = server_default
        op.add_column(_TABLE, sa.Column(col_name, col_type, **kwargs))

    if not _index_exists(bind, _TABLE, _INDEX_NAME):
        # Composite index — ascending on every column; SQLite does not
        # honour per-column direction specifiers, and PostgreSQL can scan
        # this same index for newest-first queries via index-only DESC scan.
        op.create_index(
            _INDEX_NAME,
            _TABLE,
            ["entity_type", "entity_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    if _index_exists(bind, _TABLE, _INDEX_NAME):
        op.drop_index(_INDEX_NAME, table_name=_TABLE)

    for col_name, _, _sd in reversed(_NEW_COLUMNS):
        if _column_exists(bind, _TABLE, col_name):
            op.drop_column(_TABLE, col_name)
