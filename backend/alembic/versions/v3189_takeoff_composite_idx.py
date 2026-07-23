# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""takeoff: composite (project_id, document_id) index on oe_takeoff_measurement.

Background
----------
``GET /api/v1/takeoff/measurements/?project_id=X&document_id=Y`` is the hot
path hit every time the /takeoff?tab=measurements page loads.  The table
already carries single-column B-tree indexes on both ``project_id`` and
``document_id`` (declared via ``index=True`` on the ORM columns).  PostgreSQL
can bitmap-AND two single-column indexes, but this requires two index scans
plus a heap-recheck — under concurrent load on a 1-core VPS this produced
1–2 s query latency.

A composite ``(project_id, document_id)`` index satisfies the most common
filter in a single range scan (the planner will also use its leftmost prefix
for project-only queries, so the ``ix_oe_takeoff_measurement_project_id``
single-column index becomes redundant but is intentionally kept for
downgrade safety).

The ``ORDER BY created_at DESC`` + ``OFFSET/LIMIT`` pattern remains an
unindexed sort, but with the composite index the planner only sorts the
per-(project, document) subset (typically < 500 rows), which is fast.

Safety
------
* ``CREATE INDEX CONCURRENTLY`` — zero table-lock, no app restart required.
  Alembic's ``op.create_index`` does NOT emit CONCURRENTLY by default; we
  use ``postgresql_concurrently=True`` which maps to ``CONCURRENTLY`` on
  PostgreSQL and is ignored on other dialects.
* Idempotent: guarded by an ``inspector.get_indexes`` check so re-running
  the migration (or ``alembic stamp head`` on a DB that already has the
  index from ``create_all``) is a no-op.
* Downgrade drops the composite index only; the individual single-column
  indexes pre-existed and are left untouched.

Live DDL (run on prod without restart)
---------------------------------------
    CREATE INDEX CONCURRENTLY IF NOT EXISTS
        ix_oe_takeoff_measurement_project_document
    ON oe_takeoff_measurement (project_id, document_id);

Revision ID: v3189_takeoff_composite_idx
Revises: v3188_methodology_init
Create Date: 2026-06-19

Note: the revision id is kept <= 32 chars because the create_all + ``stamp head``
bootstrap path (fresh installs and the test conftest) creates alembic's
``alembic_version.version_num`` at its default ``VARCHAR(32)`` - a longer head id
fails to stamp there with ``value too long for type character varying(32)``.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3189_takeoff_composite_idx"
down_revision: Union[str, Sequence[str], None] = "v3188_methodology_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_takeoff_measurement"
_INDEX = "ix_oe_takeoff_measurement_project_document"
_COLUMNS = ["project_id", "document_id"]


def _has_index(inspector: sa.engine.reflection.Inspector, table: str, name: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return name in {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names() or _has_index(inspector, _TABLE, _INDEX):
        return
    if bind.dialect.name == "postgresql":
        # CREATE INDEX CONCURRENTLY cannot run inside a transaction block, and
        # env.py wraps every migration in one (context.begin_transaction()).
        # autocommit_block temporarily commits the migration transaction so the
        # CONCURRENTLY build runs lock-free, then resumes it for the version stamp.
        with op.get_context().autocommit_block():
            op.create_index(
                _INDEX,
                _TABLE,
                _COLUMNS,
                postgresql_concurrently=True,
            )
    else:
        # SQLite / other dialects: CONCURRENTLY is meaningless - plain index.
        op.create_index(_INDEX, _TABLE, _COLUMNS)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_index(inspector, _TABLE, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)
