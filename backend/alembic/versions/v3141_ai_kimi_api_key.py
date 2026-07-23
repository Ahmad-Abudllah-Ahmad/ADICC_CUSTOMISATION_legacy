# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""ai: add kimi_api_key column to oe_ai_settings.

Adds support for the Kimi (Moonshot AI) provider added in PR #161
(@rjohny55). Nullable encrypted-secret column; no server_default needed.
Custom base URLs for Ollama / vLLM piggyback on the existing
``metadata`` JSON column so no further schema change is required.

Idempotent. Fresh installs that boot the app first will already have
this column from ``Base.metadata.create_all`` — running this migration
afterwards skips with an INFO log.

Revision ID: v3141_ai_kimi_api_key
Revises: v3140_qms_audit_log
Create Date: 2026-05-26
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3141_ai_kimi_api_key"
down_revision: Union[str, None] = "v3140_qms_audit_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def _column_exists(bind: sa.engine.Connection, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "oe_ai_settings", "kimi_api_key"):
        logger.info("v3141: oe_ai_settings.kimi_api_key already present, skipping")
        return
    op.add_column(
        "oe_ai_settings",
        sa.Column("kimi_api_key", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "oe_ai_settings", "kimi_api_key"):
        return
    op.drop_column("oe_ai_settings", "kimi_api_key")
