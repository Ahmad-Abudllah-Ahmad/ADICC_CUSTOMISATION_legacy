# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""ai_agents: add oe_ai_agents_custom table (user-authored agents).

Adds the ``oe_ai_agents_custom`` table that stores agents a user builds for
themselves in the AI Agents page. Custom agents carry the same presentation
and behaviour fields a built-in agent exposes (display name, tagline,
description, system prompt, category, icon, example prompts) plus the guided
builder spec the prompt was compiled from, so the edit form can re-hydrate
the friendly fields. They are scoped to their creator via ``user_id``.

The embedded-PostgreSQL runtime (the default no-Docker dev/prod path) creates
this table automatically via SQLAlchemy create_all at startup; this migration
covers external-PostgreSQL deployments that manage schema with Alembic.

Revision ID: v3152_ai_agents_custom
Revises: v3151_cost_spine
Create Date: 2026-06-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Alembic identifiers
revision = "v3152_ai_agents_custom"
down_revision = "v3151_cost_spine"
branch_labels = None
depends_on = None

_TABLE = "oe_ai_agents_custom"


def upgrade() -> None:
    """Create the oe_ai_agents_custom table if it does not already exist."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE in inspector.get_table_names():
        # Already present (e.g. created by create_all on embedded PG). Idempotent.
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("tagline", sa.String(length=280), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False, server_default="general"),
        sa.Column("icon", sa.String(length=40), nullable=False, server_default="sparkles"),
        sa.Column("example_prompts", sa.JSON(), nullable=False),
        sa.Column("guided", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oe_ai_agents_custom")),
    )
    op.create_index(
        op.f("ix_oe_ai_agents_custom_user_id"),
        _TABLE,
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the oe_ai_agents_custom table if present."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    existing_indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    if op.f("ix_oe_ai_agents_custom_user_id") in existing_indexes:
        op.drop_index(op.f("ix_oe_ai_agents_custom_user_id"), table_name=_TABLE)
    op.drop_table(_TABLE)
