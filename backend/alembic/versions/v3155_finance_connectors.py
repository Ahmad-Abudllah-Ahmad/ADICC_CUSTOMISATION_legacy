# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""TOP-30 #4: finance ERP / accounting connectors.

Adds two tables:

* ``oe_finance_connector_config`` - a configured link to an external
  accounting / ERP system (file CSV/JSON for now, transport-agnostic).
* ``oe_finance_sync_log`` - one row per sync run (push or pull, live or
  dry) for the history view.

The embedded-PostgreSQL runtime creates these via ``create_all`` at startup;
this migration covers external-PostgreSQL deployments that manage schema
with Alembic. Idempotent: it inspects existing tables first so a re-run (or
a DB the runtime already auto-created) is a no-op.

Revision ID: v3155_finance_connectors
Revises: v3154_subcontract_lien_waiver
Create Date: 2026-06-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Alembic identifiers
revision = "v3155_finance_connectors"
down_revision = "v3154_subcontract_lien_waiver"
branch_labels = None
depends_on = None

_CONFIG_TABLE = "oe_finance_connector_config"
_LOG_TABLE = "oe_finance_sync_log"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if _CONFIG_TABLE not in existing:
        op.create_table(
            _CONFIG_TABLE,
            # GUID columns are stored as VARCHAR(36) (see app.database.GUID).
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("project_id", sa.String(length=36), nullable=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("connector_type", sa.String(length=50), nullable=False),
            sa.Column("direction", sa.String(length=20), nullable=False, server_default="both"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("auto_push", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("auto_push_events", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("settings", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("credentials", sa.Text(), nullable=True),
            sa.Column("last_sync_at", sa.String(length=40), nullable=True),
            sa.Column("last_sync_status", sa.String(length=20), nullable=True),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("project_id", "name", name="uq_connector_proj_name"),
        )
        op.create_index("ix_connector_project_active", _CONFIG_TABLE, ["project_id", "is_active"])
        op.create_index(op.f("ix_oe_finance_connector_config_project_id"), _CONFIG_TABLE, ["project_id"])

    if _LOG_TABLE not in existing:
        op.create_table(
            _LOG_TABLE,
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("connector_config_id", sa.String(length=36), nullable=False),
            sa.Column("project_id", sa.String(length=36), nullable=True),
            sa.Column("direction", sa.String(length=20), nullable=False),
            sa.Column("trigger", sa.String(length=20), nullable=False),
            sa.Column("triggered_by_event", sa.String(length=80), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
            sa.Column("is_dry_run", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("records_in", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("records_out", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("file_keys", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("warnings", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("errors", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("job_run_id", sa.String(length=36), nullable=True),
            sa.Column("started_at", sa.String(length=40), nullable=False),
            sa.Column("finished_at", sa.String(length=40), nullable=True),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(
                ["connector_config_id"],
                [f"{_CONFIG_TABLE}.id"],
                ondelete="CASCADE",
            ),
        )
        op.create_index("ix_synclog_config_started", _LOG_TABLE, ["connector_config_id", "started_at"])
        op.create_index(op.f("ix_oe_finance_sync_log_connector_config_id"), _LOG_TABLE, ["connector_config_id"])
        op.create_index(op.f("ix_oe_finance_sync_log_project_id"), _LOG_TABLE, ["project_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    if _LOG_TABLE in existing:
        op.drop_table(_LOG_TABLE)
    if _CONFIG_TABLE in existing:
        op.drop_table(_CONFIG_TABLE)
