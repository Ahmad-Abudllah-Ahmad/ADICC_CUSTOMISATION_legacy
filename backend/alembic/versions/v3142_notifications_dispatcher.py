# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""notifications: webhook-target table for the Epic B dispatcher.

Adds ``oe_notification_webhook_target`` — admin-managed outbound webhook
endpoints that consume the ``notifications.dispatch.webhook`` channel.
Each row is one POST destination; ``event_filter`` is a comma-separated
list of event-type patterns (``*`` is wildcard).

Idempotent.  Fresh installs that boot the app first will already have
this table from ``Base.metadata.create_all`` — running this migration
afterwards skips with an INFO log.  Every NOT NULL column carries a
``server_default`` so the create-all path stays compatible.

Revision ID: v3142_notifications_dispatcher
Revises: v3141_ai_kimi_api_key
Create Date: 2026-05-26
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3142_notifications_dispatcher"
down_revision: Union[str, None] = "v3141_ai_kimi_api_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_TABLE = "oe_notification_webhook_target"


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, _TABLE):
        logger.info("v3142: %s already present, skipping", _TABLE)
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
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column(
            "event_filter",
            sa.String(length=1024),
            nullable=False,
            server_default="*",
        ),
        sa.Column("secret", sa.String(length=255), nullable=True),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1") if bind.dialect.name == "sqlite" else sa.text("true"),
        ),
        sa.Column("last_status", sa.Integer(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "failure_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index(
        f"ix_{_TABLE}_active",
        _TABLE,
        ["active"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, _TABLE):
        return

    try:
        op.drop_index(f"ix_{_TABLE}_active", table_name=_TABLE)
    except Exception:  # noqa: BLE001 — idempotent drop
        pass
    op.drop_table(_TABLE)
