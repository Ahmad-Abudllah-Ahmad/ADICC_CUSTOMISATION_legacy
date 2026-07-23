# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""ai_agents: persist the trust envelope on a run.

Additive only. Adds a nullable ``trust`` JSON column to ``oe_ai_agents_run`` that
stores the structured trust envelope (calibrated confidence, rationale, cited
sources, what-would-increase-confidence) parsed off a trust-enabled agent's
final answer. Persisting it lets the run view show how far to trust an answer,
and lets a later accuracy review score the AI's stated confidence against what
actually happened.

Guarded so the migration is a safe no-op on a fresh install that already built
the column via ``Base.metadata.create_all``. The downgrade drops the column.

Revision ID: v3204_ai_agents_trust
Revises: v3203_schedule_evm_snapshot
Create Date: 2026-06-24
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3204_ai_agents_trust"
down_revision: Union[str, Sequence[str], None] = "v3203_schedule_evm_snapshot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_TABLE = "oe_ai_agents_run"
_COLUMN = "trust"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if _TABLE not in insp.get_table_names():
        logger.info("v3204 ai_agents trust: %s missing, skipped", _TABLE)
        return
    columns = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN not in columns:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.JSON(), nullable=True))
        logger.info("v3204 ai_agents trust: column added")
    else:
        logger.info("v3204 ai_agents trust: column already present, no-op")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if _TABLE not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN in columns:
        op.drop_column(_TABLE, _COLUMN)
        logger.info("v3204 ai_agents trust: column dropped")
