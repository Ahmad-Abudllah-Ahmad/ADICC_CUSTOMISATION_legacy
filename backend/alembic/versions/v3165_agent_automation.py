# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Agent automation: trigger-source marker on agent runs (Item 29).

The no-code agent builder's scheduling + tool-access foundations (the
``automation`` JSON envelope on ``oe_ai_agents_custom``) already shipped in
v3157. The remaining workflow-automation delta is event-triggered runs and the
monitoring of automated runs. To tell an automated run (fired by the cron
scheduler or a platform event) apart from a manual one in the monitoring panel
and the audit trail, ``oe_ai_agents_run`` gains a ``trigger_source`` column:

    "manual"        — a user clicked Run (the default; existing rows backfill here)
    "schedule"      — the cron scheduler fired it
    "event:<name>"  — a platform event fired it (e.g. "event:rfi_created")

Indexed so the monitoring endpoint can list "all automated runs" cheaply.

The embedded PostgreSQL runtime materialises this via create_all at startup;
this migration covers external-PostgreSQL deployments that manage schema with
Alembic. Every change is inspector-guarded so a re-run, or a DB the runtime
already auto-created, is a no-op.

Revision ID: v3165_agent_automation
Revises: v3159_wave6_jobcost_leftover
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3165_agent_automation"
down_revision = "v3159_wave6_jobcost_leftover"
branch_labels = None
depends_on = None

_RUN_TABLE = "oe_ai_agents_run"
_TRIGGER_COL = "trigger_source"
_TRIGGER_IDX = "ix_oe_ai_agents_run_trigger_source"


def _cols(insp: sa.Inspector, table: str) -> set[str]:
    try:
        return {c["name"] for c in insp.get_columns(table)}
    except Exception:  # noqa: BLE001 - table absent
        return set()


def _idx(insp: sa.Inspector, table: str) -> set[str]:
    try:
        return {ix["name"] for ix in insp.get_indexes(table)}
    except Exception:  # noqa: BLE001 - table absent
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    run_cols = _cols(insp, _RUN_TABLE)
    if run_cols and _TRIGGER_COL not in run_cols:
        # server_default backfills existing rows to "manual" (they were all
        # user-initiated). The ORM default keeps new inserts honest.
        op.add_column(
            _RUN_TABLE,
            sa.Column(
                _TRIGGER_COL,
                sa.String(length=40),
                nullable=False,
                server_default="manual",
            ),
        )
        if _TRIGGER_IDX not in _idx(insp, _RUN_TABLE):
            op.create_index(_TRIGGER_IDX, _RUN_TABLE, [_TRIGGER_COL])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if _TRIGGER_IDX in _idx(insp, _RUN_TABLE):
        op.drop_index(_TRIGGER_IDX, table_name=_RUN_TABLE)
    if _TRIGGER_COL in _cols(insp, _RUN_TABLE):
        op.drop_column(_RUN_TABLE, _TRIGGER_COL)
