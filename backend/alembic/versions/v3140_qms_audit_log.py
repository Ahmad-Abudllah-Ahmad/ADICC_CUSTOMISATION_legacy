# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""qms: append-only audit-log table for FSM transitions.

Adds ``oe_qms_audit_log`` — a QMS-scoped activity log keyed on
``(entity_type, entity_id)`` so dispute timelines for NCRs, inspections,
punch items, audits, and ITP plans can be reproduced offline (ISO 9001
§9.3, FIDIC, SCL Protocol). Sibling to the older system-wide
``oe_activity_log`` (v3033) but isolated so a per-tenant GDPR purge can
wipe quality records without touching cross-module activity.

Idempotent. Fresh installs that boot the app first will already have
this table from ``Base.metadata.create_all`` — running this migration
afterwards is a no-op. Every NOT NULL column carries a ``server_default``
so the ``create_all`` path stays compatible.

Revision ID: v3140_qms_audit_log
Revises: v3139_progress_init
Create Date: 2026-05-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3140_qms_audit_log"
down_revision: Union[str, Sequence[str], None] = "v3139_progress_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_qms_audit_log"


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, _TABLE):
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("old_status", sa.String(length=64), nullable=True),
        sa.Column("new_status", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "before_state",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "after_state",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_index(
        f"ix_{_TABLE}_tenant_id",
        _TABLE,
        ["tenant_id"],
    )
    op.create_index(
        f"ix_{_TABLE}_entity_type",
        _TABLE,
        ["entity_type"],
    )
    op.create_index(
        f"ix_{_TABLE}_entity_id",
        _TABLE,
        ["entity_id"],
    )
    op.create_index(
        "ix_qms_audit_log_entity",
        _TABLE,
        ["entity_type", "entity_id"],
    )
    op.create_index(
        "ix_qms_audit_log_tenant_created",
        _TABLE,
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, _TABLE):
        return

    # ``if_exists`` keeps each drop idempotent without a try/except that
    # swallows the error. On PostgreSQL a failed ``DROP INDEX`` (e.g. an
    # index that create_all never made) aborts the whole transaction, so a
    # caught-and-ignored failure would poison every later statement,
    # including the ``drop_table`` below.
    for idx in (
        "ix_qms_audit_log_tenant_created",
        "ix_qms_audit_log_entity",
        f"ix_{_TABLE}_entity_id",
        f"ix_{_TABLE}_entity_type",
        f"ix_{_TABLE}_tenant_id",
    ):
        op.drop_index(idx, table_name=_TABLE, if_exists=True)
    op.drop_table(_TABLE)
