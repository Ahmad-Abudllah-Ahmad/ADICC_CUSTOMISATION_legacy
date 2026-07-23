# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""schedule T2.3: hierarchical activity codes, UDFs and saved layouts.

Adds one scope-consistent persistence layer for slicing large schedules:

* ``oe_schedule_code_dictionary`` - a named code dimension scoped to ONE project
  (workspace "library" templates carry ``is_library=True`` + NULL project_id and
  are copied into a project, never referenced live).
* ``oe_schedule_code_value`` - a node in a dictionary's value tree (self-parented).
* ``oe_schedule_code_assignment`` - one value of a dictionary assigned to an
  activity (single-valued in v1).
* ``oe_schedule_udf`` - a typed user-defined field definition per project.
* ``oe_schedule_udf_value`` - one activity's value for one UDF, in the typed
  column matching its kind (so the grouped query can ORDER/GROUP natively).
* ``oe_schedule_layout`` - a saved schedule view (columns, grouping, sort,
  filters, bar styling) with the same private/project/workspace sharing as
  saved_views.

Every operation is guarded so the migration is a safe no-op on a fresh install
that already booted the app (``Base.metadata.create_all`` builds the full current
schema). The downgrade fully reverses the upgrade.

Revision ID: v3197_schedule_activity_codes
Revises: v3196_schedule_delay_analysis
Create Date: 2026-06-23
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3197_schedule_activity_codes"
down_revision: Union[str, Sequence[str], None] = "v3196_schedule_delay_analysis"
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


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


# (table, index_name, [columns]) for every non-unique index the ORM declares.
_INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    ("oe_schedule_code_dictionary", "ix_sched_codedict_project", ["project_id"]),
    ("oe_schedule_code_value", "ix_sched_codeval_dict", ["dictionary_id"]),
    ("oe_schedule_code_value", "ix_sched_codeval_parent", ["parent_id"]),
    ("oe_schedule_code_assignment", "ix_sched_codeassign_value", ["dictionary_id", "value_id"]),
    ("oe_schedule_code_assignment", "ix_sched_codeassign_activity", ["activity_id"]),
    ("oe_schedule_udf", "ix_sched_udf_project", ["project_id"]),
    ("oe_schedule_udf_value", "ix_sched_udfval_udf_text", ["udf_id", "value_text"]),
    ("oe_schedule_udf_value", "ix_sched_udfval_udf_number", ["udf_id", "value_number"]),
    ("oe_schedule_udf_value", "ix_sched_udfval_udf_date", ["udf_id", "value_date"]),
    ("oe_schedule_udf_value", "ix_sched_udfval_activity", ["activity_id"]),
    ("oe_schedule_layout", "ix_sched_layout_schedule", ["schedule_id"]),
    ("oe_schedule_layout", "ix_sched_layout_project", ["project_id"]),
    ("oe_schedule_layout", "ix_sched_layout_owner", ["owner_id"]),
)


def upgrade() -> None:
    bind = op.get_bind()

    # ── code dictionary (parent of values/assignments) ───────────────────────
    if not _table_exists(bind, "oe_schedule_code_dictionary"):
        op.create_table(
            "oe_schedule_code_dictionary",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("is_library", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("color_band", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("project_id", "name", name="uq_sched_codedict_project_name"),
        )

    # ── code value (self-parented tree) ──────────────────────────────────────
    if not _table_exists(bind, "oe_schedule_code_value"):
        op.create_table(
            "oe_schedule_code_value",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "dictionary_id",
                sa.String(length=36),
                sa.ForeignKey("oe_schedule_code_dictionary.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "parent_id",
                sa.String(length=36),
                sa.ForeignKey("oe_schedule_code_value.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("code", sa.String(length=100), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("color", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("dictionary_id", "parent_id", "code", name="uq_sched_codeval_dict_parent_code"),
        )

    # ── code assignment (activity <-> value) ─────────────────────────────────
    if not _table_exists(bind, "oe_schedule_code_assignment"):
        op.create_table(
            "oe_schedule_code_assignment",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "activity_id",
                sa.String(length=36),
                sa.ForeignKey("oe_schedule_activity.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "dictionary_id",
                sa.String(length=36),
                sa.ForeignKey("oe_schedule_code_dictionary.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "value_id",
                sa.String(length=36),
                sa.ForeignKey("oe_schedule_code_value.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.UniqueConstraint("activity_id", "dictionary_id", name="uq_sched_codeassign_activity_dict"),
        )

    # ── UDF definition ───────────────────────────────────────────────────────
    if not _table_exists(bind, "oe_schedule_udf"):
        op.create_table(
            "oe_schedule_udf",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("key", sa.String(length=64), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("value_type", sa.String(length=16), nullable=False, server_default="text"),
            sa.Column("enum_values", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("project_id", "key", name="uq_sched_udf_project_key"),
        )

    # ── UDF value (typed columns) ────────────────────────────────────────────
    if not _table_exists(bind, "oe_schedule_udf_value"):
        op.create_table(
            "oe_schedule_udf_value",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "activity_id",
                sa.String(length=36),
                sa.ForeignKey("oe_schedule_activity.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "udf_id",
                sa.String(length=36),
                sa.ForeignKey("oe_schedule_udf.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("value_text", sa.Text(), nullable=True),
            sa.Column("value_number", sa.Numeric(18, 4), nullable=True),
            sa.Column("value_date", sa.String(length=20), nullable=True),
            sa.Column("value_bool", sa.Boolean(), nullable=True),
            sa.UniqueConstraint("activity_id", "udf_id", name="uq_sched_udfval_activity_udf"),
        )

    # ── saved layout ─────────────────────────────────────────────────────────
    if not _table_exists(bind, "oe_schedule_layout"):
        op.create_table(
            "oe_schedule_layout",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "owner_id",
                sa.String(length=36),
                sa.ForeignKey("oe_users_user.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "schedule_id",
                sa.String(length=36),
                sa.ForeignKey("oe_schedule_schedule.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("share_scope", sa.String(length=16), nullable=False, server_default="private"),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("spec", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("owner_id", "schedule_id", "name", name="uq_sched_layout_owner_schedule_name"),
        )

    # ── Indexes ──────────────────────────────────────────────────────────────
    for table, index_name, columns in _INDEXES:
        if _table_exists(bind, table) and not _index_exists(bind, table, index_name):
            op.create_index(index_name, table, columns)

    logger.info("v3197 schedule activity codes: 6 tables + indexes ensured")


def downgrade() -> None:
    bind = op.get_bind()

    # Child tables before parents (FK order).
    _drop_plan: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "oe_schedule_layout",
            ("ix_sched_layout_owner", "ix_sched_layout_project", "ix_sched_layout_schedule"),
        ),
        (
            "oe_schedule_udf_value",
            (
                "ix_sched_udfval_activity",
                "ix_sched_udfval_udf_date",
                "ix_sched_udfval_udf_number",
                "ix_sched_udfval_udf_text",
            ),
        ),
        ("oe_schedule_udf", ("ix_sched_udf_project",)),
        (
            "oe_schedule_code_assignment",
            ("ix_sched_codeassign_activity", "ix_sched_codeassign_value"),
        ),
        (
            "oe_schedule_code_value",
            ("ix_sched_codeval_parent", "ix_sched_codeval_dict"),
        ),
        ("oe_schedule_code_dictionary", ("ix_sched_codedict_project",)),
    )
    for table, indexes in _drop_plan:
        if _table_exists(bind, table):
            for index_name in indexes:
                if _index_exists(bind, table, index_name):
                    op.drop_index(index_name, table_name=table)
            op.drop_table(table)

    logger.info("v3197 schedule activity codes: reverted")
