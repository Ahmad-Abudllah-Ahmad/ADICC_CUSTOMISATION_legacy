# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""v3-P10b — match session construction_stage pin.

Adds the nullable ``construction_stage`` column to
``oe_match_elements_session`` so the user-picked stage from the
/match-elements UI dropdown is durable across page reloads. The column
also drives the SearchPlan ``construction_stage`` hard filter when the
ranker stamps it onto the envelope at run-match time.

Idempotent — re-applying on an already-migrated DB skips the column.

Revision ID: v2935_match_session_stage
Revises: v2934_match_search_log
Create Date: 2026-05-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v2935_match_session_stage"
down_revision: Union[str, Sequence[str], None] = "v2934_match_search_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "oe_match_elements_session"
_COLUMN = "construction_stage"


def _has_column(inspector: sa.engine.reflection.Inspector, table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_column(inspector, _TABLE, _COLUMN):
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.String(32), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, _TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
