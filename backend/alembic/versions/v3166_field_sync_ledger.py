# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""TOP-30 #14: durable offline-sync idempotency ledger for the field PWA.

The offline field shell tags every queued mutation with a device-generated
``client_op_id`` and replays the queue when connectivity returns. That replay is
at-least-once: a reconnect that fires twice, or a write whose response was lost
to a dropped link, both re-send the same op. The diary entry create was already
idempotent (its ``(project, author, date)`` unique constraint), but the activity
append was not, so a double drain inserted duplicate logged hours, which then
fed duplicate labour rows into payroll.

This migration adds ``oe_field_sync_ledger`` - one row per applied offline op,
unique on ``client_op_id``, pointing at the row the op produced. The service
checks the ledger before inserting an activity and returns the original row on a
replay, making the whole capture replay-safe end to end.

It also merges the two open Alembic heads (``v3160_field_time_payroll`` and
``v3165_agent_automation``, both of which branched off ``v3159``) back into a
single linear head, and adds the ``field_source`` marker column on
``oe_field_diary_entry`` so external-PostgreSQL deployments match the ORM.

The embedded PostgreSQL runtime materialises all of this via create_all at
startup; this migration covers external-PostgreSQL deployments that manage
schema with Alembic. Every change is inspector-guarded so a re-run, or a DB the
runtime already auto-created, is a no-op. GUID columns are VARCHAR(36) (the
app.database.GUID TypeDecorator impl on PostgreSQL).

Revision ID: v3166_field_sync_ledger
Revises: v3160_field_time_payroll, v3165_agent_automation
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3166_field_sync_ledger"
# Merge the two heads that both branched off v3159 back to one linear head.
down_revision = ("v3160_field_time_payroll", "v3165_agent_automation")
branch_labels = None
depends_on = None

_LEDGER_TABLE = "oe_field_sync_ledger"
_ENTRY_TABLE = "oe_field_diary_entry"


def _has_table(insp: sa.Inspector, table: str) -> bool:
    try:
        return insp.has_table(table)
    except Exception:  # noqa: BLE001
        return False


def _cols(insp: sa.Inspector, table: str) -> set[str]:
    try:
        return {c["name"] for c in insp.get_columns(table)}
    except Exception:  # noqa: BLE001 - table absent
        return set()


def _idx(insp: sa.Inspector, table: str) -> set[str]:
    try:
        return {ix["name"] for ix in insp.get_indexes(table)}
    except Exception:  # noqa: BLE001
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1) The sync ledger. Created whole only when absent (the runtime may have
    #    already built it via create_all).
    if not _has_table(insp, _LEDGER_TABLE):
        op.create_table(
            _LEDGER_TABLE,
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("client_op_id", sa.String(length=128), nullable=False),
            sa.Column("project_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column(
                "op_kind",
                sa.String(length=64),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "result_type",
                sa.String(length=64),
                nullable=False,
                server_default="",
            ),
            sa.Column("result_id", sa.String(length=36), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["project_id"],
                ["oe_projects_project.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["oe_users_user.id"],
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "client_op_id",
                name="uq_oe_field_sync_ledger_client_op_id",
            ),
        )
        op.create_index(
            "ix_oe_field_sync_ledger_client_op_id",
            _LEDGER_TABLE,
            ["client_op_id"],
        )
        op.create_index(
            "ix_oe_field_sync_ledger_project_user",
            _LEDGER_TABLE,
            ["project_id", "user_id"],
        )
        op.create_index(
            "ix_oe_field_sync_ledger_project_id",
            _LEDGER_TABLE,
            ["project_id"],
        )
        op.create_index(
            "ix_oe_field_sync_ledger_user_id",
            _LEDGER_TABLE,
            ["user_id"],
        )
    else:
        # Table exists but a guard for the unique index in case an older partial
        # create_all landed without it.
        ledger_idx = _idx(insp, _LEDGER_TABLE)
        if "ix_oe_field_sync_ledger_client_op_id" not in ledger_idx:
            op.create_index(
                "ix_oe_field_sync_ledger_client_op_id",
                _LEDGER_TABLE,
                ["client_op_id"],
            )

    # 2) field_source marker on the diary entry (added to the ORM without a
    #    standalone migration). Nullable, no default - absent means "not
    #    field-captured".
    entry_cols = _cols(insp, _ENTRY_TABLE)
    if entry_cols and "field_source" not in entry_cols:
        op.add_column(
            _ENTRY_TABLE,
            sa.Column("field_source", sa.String(length=16), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "field_source" in _cols(insp, _ENTRY_TABLE):
        op.drop_column(_ENTRY_TABLE, "field_source")

    if _has_table(insp, _LEDGER_TABLE):
        for ix in (
            "ix_oe_field_sync_ledger_user_id",
            "ix_oe_field_sync_ledger_project_id",
            "ix_oe_field_sync_ledger_project_user",
            "ix_oe_field_sync_ledger_client_op_id",
        ):
            if ix in _idx(insp, _LEDGER_TABLE):
                op.drop_index(ix, table_name=_LEDGER_TABLE)
        op.drop_table(_LEDGER_TABLE)
