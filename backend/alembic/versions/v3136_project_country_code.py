# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Wave 28 — add country_code to oe_projects_project.

Required by the calendar-aware CPM engine introduced in Wave 28 so the
schedule engine can resolve the correct public-holiday set when computing
calendar finish dates from CPM work-day indices.

* Column: ``country_code VARCHAR(2)``
* Default: ``'DE'`` (server-side default so existing rows are auto-filled)
* Nullable: False (server_default guarantees a value for all rows)

Strictly-additive; no existing data is rewritten.  The ``ADD COLUMN``
statement is idempotent via inspector guard on both PostgreSQL and SQLite.

Revision ID: v3136_project_country_code
Revises: v3135_project_unit_system
Create Date: 2026-05-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3136_project_country_code"
down_revision: Union[str, Sequence[str], None] = "v3135_project_unit_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_projects_project"
_COL = "country_code"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    if _COL not in existing_cols:
        op.add_column(
            _TABLE,
            sa.Column(
                _COL,
                sa.String(2),
                nullable=False,
                server_default="DE",
                comment="ISO 3166-1 alpha-2 country code; used by CPM calendar engine",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    if _COL in existing_cols:
        op.drop_column(_TABLE, _COL)
