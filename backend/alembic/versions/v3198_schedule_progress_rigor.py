# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""schedule T3.2: progress rigor (% types, steps, suspend/resume, calendars).

Additive only. Extends ``oe_schedule_activity`` with the progress-rigor columns
and adds the weighted-step table ``oe_schedule_activity_step``:

* ``percent_complete_type`` - physical (== today, default) / duration / units.
* ``remaining_duration`` - working days; ``NULL`` => derive from ``progress_pct``.
* ``budgeted_units`` / ``installed_units`` - read only for the ``units`` type.
* ``calendar_id`` - per-activity working calendar (plain GUID, no DB FK; the
  resolver falls back to the default calendar when unset / dangling).
* ``suspended_at`` / ``resumed_at`` / ``suspend_reason`` - suspend/resume audit
  (status gains a ``suspended`` value - not a column).

Existing rows backfill to ``percent_complete_type='physical'`` and
``remaining_duration=NULL`` (identical to today's behaviour). Every operation is
guarded so the migration is a safe no-op on a fresh install that already booted
the app (``Base.metadata.create_all`` builds the current schema). The downgrade
fully reverses the upgrade.

Revision ID: v3198_schedule_progress_rigor
Revises: v3197_schedule_activity_codes
Create Date: 2026-06-23
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3198_schedule_progress_rigor"
down_revision: Union[str, Sequence[str], None] = "v3197_schedule_activity_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_ACTIVITY = "oe_schedule_activity"
_STEP = "oe_schedule_activity_step"


def _table_exists(bind: sa.engine.Connection, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def _index_exists(bind: sa.engine.Connection, table: str, index: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(ix["name"] == index for ix in insp.get_indexes(table))


def _column_exists(bind: sa.engine.Connection, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


# (column, sa type, kwargs) for the additive Activity columns.
_ACTIVITY_COLUMNS: tuple[tuple[str, sa.types.TypeEngine, dict], ...] = (
    ("percent_complete_type", sa.String(length=16), {"nullable": False, "server_default": "physical"}),
    ("remaining_duration", sa.Integer(), {"nullable": True}),
    ("budgeted_units", sa.Numeric(18, 4), {"nullable": True}),
    ("installed_units", sa.Numeric(18, 4), {"nullable": True}),
    ("calendar_id", sa.String(length=36), {"nullable": True}),
    ("suspended_at", sa.String(length=40), {"nullable": True}),
    ("resumed_at", sa.String(length=40), {"nullable": True}),
    ("suspend_reason", sa.Text(), {"nullable": True}),
)

# (index_name, [columns]) for the Activity index=True columns.
_ACTIVITY_INDEXES: tuple[tuple[str, list[str]], ...] = (
    ("ix_oe_schedule_activity_percent_complete_type", ["percent_complete_type"]),
    ("ix_oe_schedule_activity_calendar_id", ["calendar_id"]),
)


def upgrade() -> None:
    bind = op.get_bind()

    # ── Additive columns on the activity table ───────────────────────────────
    if _table_exists(bind, _ACTIVITY):
        for name, col_type, kwargs in _ACTIVITY_COLUMNS:
            if not _column_exists(bind, _ACTIVITY, name):
                op.add_column(_ACTIVITY, sa.Column(name, col_type, **kwargs))
        for index_name, columns in _ACTIVITY_INDEXES:
            if not _index_exists(bind, _ACTIVITY, index_name):
                op.create_index(index_name, _ACTIVITY, columns)

    # ── Weighted progress-step table ─────────────────────────────────────────
    if not _table_exists(bind, _STEP):
        op.create_table(
            _STEP,
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column(
                "activity_id",
                sa.String(length=36),
                sa.ForeignKey("oe_schedule_activity.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("weight", sa.Numeric(10, 4), nullable=False, server_default="1"),
            sa.Column("percent_complete", sa.Numeric(6, 3), nullable=False, server_default="0"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_milestone", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.CheckConstraint("weight >= 0", name="ck_sched_step_weight_nonneg"),
            sa.CheckConstraint(
                "percent_complete >= 0 AND percent_complete <= 100",
                name="ck_sched_step_pct_range",
            ),
        )

    if _table_exists(bind, _STEP) and not _index_exists(bind, _STEP, "ix_sched_step_activity_order"):
        op.create_index("ix_sched_step_activity_order", _STEP, ["activity_id", "sort_order"])

    logger.info("v3198 schedule progress rigor: activity columns + step table ensured")


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, _STEP):
        if _index_exists(bind, _STEP, "ix_sched_step_activity_order"):
            op.drop_index("ix_sched_step_activity_order", table_name=_STEP)
        op.drop_table(_STEP)

    if _table_exists(bind, _ACTIVITY):
        for index_name, _columns in _ACTIVITY_INDEXES:
            if _index_exists(bind, _ACTIVITY, index_name):
                op.drop_index(index_name, table_name=_ACTIVITY)
        for name, _col_type, _kwargs in reversed(_ACTIVITY_COLUMNS):
            if _column_exists(bind, _ACTIVITY, name):
                op.drop_column(_ACTIVITY, name)

    logger.info("v3198 schedule progress rigor: reverted")
