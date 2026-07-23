# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""change family: ball-in-court + response due date.

Additive only. Adds two nullable columns to each change-management entity so
every change record carries a consistent "who owes the next action, and by
when":

* ``ball_in_court`` (String(36)) - the user id of whoever must act next.
* ``response_due_date`` (String(40)) - when that action is due (ISO-8601).

Tables touched: ``oe_variations_notice``, ``oe_variations_request``,
``oe_variations_order``, ``oe_moc_entry``, ``oe_changeorders_order``. These two
fields are the foundation for cross-module change cycle-time telemetry and make
the records answerable to "what is waiting on me".

Every operation is guarded so the migration is a safe no-op on a fresh install
that already built the columns via ``Base.metadata.create_all``. The downgrade
drops the columns.

Revision ID: v3206_change_ball_in_court
Revises: v3205_approval_delegation
Create Date: 2026-06-24
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3206_change_ball_in_court"
down_revision: Union[str, Sequence[str], None] = "v3205_approval_delegation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_TABLES: tuple[str, ...] = (
    "oe_variations_notice",
    "oe_variations_request",
    "oe_variations_order",
    "oe_moc_entry",
    "oe_changeorders_order",
)
_BALL = "ball_in_court"
_DUE = "response_due_date"


def _columns(bind: sa.engine.Connection, table: str) -> set[str]:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    table_names = set(sa.inspect(bind).get_table_names())
    for table in _TABLES:
        if table not in table_names:
            logger.info("v3206 change ball-in-court: %s missing, skipped", table)
            continue
        cols = _columns(bind, table)
        if _BALL not in cols:
            op.add_column(table, sa.Column(_BALL, sa.String(length=36), nullable=True))
        if _DUE not in cols:
            op.add_column(table, sa.Column(_DUE, sa.String(length=40), nullable=True))
    logger.info("v3206 change ball-in-court: columns ensured")


def downgrade() -> None:
    bind = op.get_bind()
    table_names = set(sa.inspect(bind).get_table_names())
    for table in _TABLES:
        if table not in table_names:
            continue
        cols = _columns(bind, table)
        if _DUE in cols:
            op.drop_column(table, _DUE)
        if _BALL in cols:
            op.drop_column(table, _BALL)
    logger.info("v3206 change ball-in-court: reverted")
