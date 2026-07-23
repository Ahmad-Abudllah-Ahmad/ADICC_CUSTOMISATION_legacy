# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""bim: optional folder label on saved smart views and element groups.

Additive only. Adds a nullable ``folder`` column to ``oe_smart_view`` and
``oe_bim_element_group`` so users can organise their saved filters and
selection sets into named folders in the model view. NULL or empty means the
item is ungrouped; existing rows keep ``folder = NULL`` and nothing is moved.
Money-free.

Every operation is guarded so the migration is a safe no-op on a fresh install
that already built the columns via ``Base.metadata.create_all``. The downgrade
drops the columns.

Revision ID: v3215_bim_view_folders
Revises: v3214_project_status_history
Create Date: 2026-06-29
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3215_bim_view_folders"
down_revision: Union[str, Sequence[str], None] = "v3214_project_status_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_TARGETS: tuple[str, ...] = ("oe_smart_view", "oe_bim_element_group")
_COLUMN = "folder"


def _table_exists(bind: sa.engine.Connection, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def _column_exists(bind: sa.engine.Connection, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    for table in _TARGETS:
        if _table_exists(bind, table) and not _column_exists(bind, table, _COLUMN):
            op.add_column(table, sa.Column(_COLUMN, sa.String(255), nullable=True))
    logger.info("v3215 bim view folders: schema ensured")


def downgrade() -> None:
    bind = op.get_bind()
    for table in _TARGETS:
        if _table_exists(bind, table) and _column_exists(bind, table, _COLUMN):
            op.drop_column(table, _COLUMN)
    logger.info("v3215 bim view folders: reverted")
