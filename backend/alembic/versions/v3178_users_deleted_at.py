# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Add the GDPR Art. 17 erasure marker column to the users table.

Adds a single additive, nullable column:

    oe_users_user.deleted_at   - timestamp set when the account holder erases
                                 their own account via DELETE /api/v1/users/me.
                                 NULL means a live account. The erasure path
                                 anonymises the row in place (PII nulled,
                                 password hash invalidated, is_active flipped
                                 False) rather than hard deleting it, so the
                                 user's foreign-key references (projects,
                                 activity, audit) stay intact while no personal
                                 data remains and the account can no longer log
                                 in.

The embedded PostgreSQL runtime materialises new columns via create_all and
auto-heals at startup, so this migration is for external PostgreSQL deployments
that manage schema with Alembic. The step is guarded with a presence check so a
re-run, or a DB the runtime already auto-created, is a no-op. Additive and
backfill-safe (existing rows read NULL = live). PostgreSQL-only.

Revision ID: v3178_users_deleted_at
Revises: v3177_ai_takeoff_plan_read
Create Date: 2026-06-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3178_users_deleted_at"
down_revision = "v3177_ai_takeoff_plan_read"
branch_labels = None
depends_on = None

_TABLE = "oe_users_user"
_COLUMN = "deleted_at"


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _has_column(_TABLE, _COLUMN):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    if _has_column(_TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
