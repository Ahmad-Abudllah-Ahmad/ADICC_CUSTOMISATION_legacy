# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""schedule_advanced T2.2: forensic delay-analysis persistence.

Adds the persistent spine for guided forensic delay analysis:

* ``oe_schedule_advanced_delay_analysis`` - one forensic run (method, baseline /
  as-built refs, out-of-sequence mode, apportionment method, totals, the cached
  exhibit ``result_json``, and the e-signed issue fields).
* ``oe_schedule_advanced_delay_event`` - a discrete causative event (party
  responsibility, concurrency / pacing flags, the impacted activity ref, and the
  engine-facing work-day window).
* ``oe_schedule_advanced_fragnet`` - the schedule fragment for an event's network
  impact (insert mode, added duration, fragnet activities + edge rewires).
* ``oe_schedule_advanced_delay_window`` - one computed analysis window with its
  responsibility attribution.

Also adds one additive column ``delay_analysis_id`` to ``oe_variations_eot_claim``
so an Extension-of-Time claim can soft-link back to the analysis it was raised
from (plain GUID, no cross-module FK).

Every operation is guarded so the migration is a safe no-op on a fresh install
that already booted the app (``Base.metadata.create_all`` builds the full current
schema). The downgrade fully reverses the upgrade.

Revision ID: v3196_schedule_delay_analysis
Revises: v3195_cc_handover
Create Date: 2026-06-23
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3196_schedule_delay_analysis"
down_revision: Union[str, Sequence[str], None] = "v3195_cc_handover"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


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


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


# (table, index_name, [columns]) for every index the ORM declares via index=True.
_INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    (
        "oe_schedule_advanced_delay_analysis",
        "ix_oe_schedule_advanced_delay_analysis_project_id",
        ["project_id"],
    ),
    (
        "oe_schedule_advanced_delay_analysis",
        "ix_oe_schedule_advanced_delay_analysis_schedule_id",
        ["schedule_id"],
    ),
    (
        "oe_schedule_advanced_delay_analysis",
        "ix_oe_schedule_advanced_delay_analysis_status",
        ["status"],
    ),
    (
        "oe_schedule_advanced_delay_event",
        "ix_oe_schedule_advanced_delay_event_analysis_id",
        ["analysis_id"],
    ),
    (
        "oe_schedule_advanced_fragnet",
        "ix_oe_schedule_advanced_fragnet_delay_event_id",
        ["delay_event_id"],
    ),
    (
        "oe_schedule_advanced_delay_window",
        "ix_oe_schedule_advanced_delay_window_analysis_id",
        ["analysis_id"],
    ),
)


def upgrade() -> None:
    bind = op.get_bind()

    # ── Table: forensic delay analysis run ───────────────────────────────────
    if not _table_exists(bind, "oe_schedule_advanced_delay_analysis"):
        op.create_table(
            "oe_schedule_advanced_delay_analysis",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("schedule_id", sa.String(length=36), nullable=True),
            sa.Column("method", sa.String(length=40), nullable=False, server_default="tia"),
            sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("as_planned_baseline_id", sa.String(length=36), nullable=True),
            sa.Column("as_built_snapshot_id", sa.String(length=36), nullable=True),
            sa.Column("oos_mode", sa.String(length=20), nullable=False, server_default="retained_logic"),
            sa.Column("data_date", sa.String(length=40), nullable=True),
            sa.Column("apportionment_method", sa.String(length=40), nullable=False, server_default="malmaison"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
            sa.Column("window_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_entitlement_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("concurrent_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("result_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("issued_at", sa.String(length=40), nullable=True),
            sa.Column("issued_by", sa.String(length=36), nullable=True),
            sa.Column("signature_sha256", sa.String(length=64), nullable=True),
            sa.Column("signature_snapshot", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("eot_claim_id", sa.String(length=36), nullable=True),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        )

    # ── Table: delay event ───────────────────────────────────────────────────
    if not _table_exists(bind, "oe_schedule_advanced_delay_event"):
        op.create_table(
            "oe_schedule_advanced_delay_event",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "analysis_id",
                sa.String(length=36),
                sa.ForeignKey("oe_schedule_advanced_delay_analysis.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("code", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("title", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("root_cause", sa.Text(), nullable=False, server_default=""),
            sa.Column("responsibility", sa.String(length=20), nullable=False, server_default="employer"),
            sa.Column("risk_event_category", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("is_concurrent", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("concurrency_group", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("is_pacing", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("source_ref_type", sa.String(length=40), nullable=True),
            sa.Column("source_ref_id", sa.String(length=36), nullable=True),
            sa.Column("insert_at_activity_ref", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("event_start", sa.String(length=40), nullable=True),
            sa.Column("event_end", sa.String(length=40), nullable=True),
            sa.Column("start_workday", sa.Integer(), nullable=True),
            sa.Column("end_workday", sa.Integer(), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        )

    # ── Table: fragnet ───────────────────────────────────────────────────────
    if not _table_exists(bind, "oe_schedule_advanced_fragnet"):
        op.create_table(
            "oe_schedule_advanced_fragnet",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "delay_event_id",
                sa.String(length=36),
                sa.ForeignKey("oe_schedule_advanced_delay_event.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("insert_mode", sa.String(length=20), nullable=False, server_default="lengthen_activity"),
            sa.Column("insert_at_activity_ref", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("added_duration_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("fragnet_activities", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("rewires", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("applies_in_window", sa.Integer(), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        )

    # ── Table: delay window ──────────────────────────────────────────────────
    if not _table_exists(bind, "oe_schedule_advanced_delay_window"):
        op.create_table(
            "oe_schedule_advanced_delay_window",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "analysis_id",
                sa.String(length=36),
                sa.ForeignKey("oe_schedule_advanced_delay_analysis.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("sequence_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("window_start", sa.String(length=40), nullable=True),
            sa.Column("window_end", sa.String(length=40), nullable=True),
            sa.Column("finish_at_open", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("finish_at_close", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("gross_slip_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("employer_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("contractor_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("neutral_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("concurrent_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("net_entitlement_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("narrative", sa.Text(), nullable=False, server_default=""),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        )

    # ── Additive column: EOT claim back-link ─────────────────────────────────
    if _table_exists(bind, "oe_variations_eot_claim") and not _column_exists(
        bind, "oe_variations_eot_claim", "delay_analysis_id"
    ):
        op.add_column(
            "oe_variations_eot_claim",
            sa.Column("delay_analysis_id", sa.String(length=36), nullable=True),
        )

    # ── Indexes ──────────────────────────────────────────────────────────────
    for table, index_name, columns in _INDEXES:
        if _table_exists(bind, table) and not _index_exists(bind, table, index_name):
            op.create_index(index_name, table, columns)

    logger.info("v3196 schedule_advanced delay analysis: 4 tables + EOT column + indexes ensured")


def downgrade() -> None:
    bind = op.get_bind()

    # Drop the EOT back-link column first.
    if _table_exists(bind, "oe_variations_eot_claim") and _column_exists(
        bind, "oe_variations_eot_claim", "delay_analysis_id"
    ):
        op.drop_column("oe_variations_eot_claim", "delay_analysis_id")

    # Child tables before parents (FK order).
    _drop_plan: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "oe_schedule_advanced_fragnet",
            ("ix_oe_schedule_advanced_fragnet_delay_event_id",),
        ),
        (
            "oe_schedule_advanced_delay_window",
            ("ix_oe_schedule_advanced_delay_window_analysis_id",),
        ),
        (
            "oe_schedule_advanced_delay_event",
            ("ix_oe_schedule_advanced_delay_event_analysis_id",),
        ),
        (
            "oe_schedule_advanced_delay_analysis",
            (
                "ix_oe_schedule_advanced_delay_analysis_status",
                "ix_oe_schedule_advanced_delay_analysis_schedule_id",
                "ix_oe_schedule_advanced_delay_analysis_project_id",
            ),
        ),
    )
    for table, indexes in _drop_plan:
        if _table_exists(bind, table):
            for index_name in indexes:
                if _index_exists(bind, table, index_name):
                    op.drop_index(index_name, table_name=table)
            op.drop_table(table)

    logger.info("v3196 schedule_advanced delay analysis: reverted")
