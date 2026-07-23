# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""construction_control Pillar 3: as-built / verified records.

Adds the as-built table to the construction-control module:

* ``oe_cc_asbuilt_record`` - the verified-record wrapper: ties a survey, scan or
  measurement to a model element with explicit metrology (instrument, accuracy class,
  coordinate system), judges the captured value against an acceptance criterion, and
  carries a deliberately separate ``valid_for_legal_record`` attestation captured with an
  e-signature. An out-of-tolerance survey raises a workmanship NCR.

The captured element is linked through the shared Universal Element Reference
(``oe_cc_element_ref`` from v3191) via the polymorphic ``owner_type`` value ``asbuilt`` -
no schema change there. Every operation is guarded so the migration is a safe no-op on a
fresh install that already booted the app (``Base.metadata.create_all`` builds the full
current schema). The downgrade fully reverses the upgrade.

Revision ID: v3193_cc_asbuilt
Revises: v3192_cc_materials_test_results
Create Date: 2026-06-22
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3193_cc_asbuilt"
down_revision: Union[str, Sequence[str], None] = "v3192_cc_materials_test_results"
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


# (table, index_name, [columns]) for every index the ORM declares.
_INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    ("oe_cc_asbuilt_record", "ix_oe_cc_asbuilt_project", ["project_id"]),
    ("oe_cc_asbuilt_record", "ix_oe_cc_asbuilt_project_status", ["project_id", "status"]),
    ("oe_cc_asbuilt_record", "ix_oe_cc_asbuilt_criterion", ["criterion_id"]),
    ("oe_cc_asbuilt_record", "ix_oe_cc_asbuilt_source", ["source_kind", "source_ref"]),
    ("oe_cc_asbuilt_record", "ix_oe_cc_asbuilt_raised_ncr", ["raised_ncr_id"]),
)


def upgrade() -> None:
    bind = op.get_bind()

    # ── Table: as-built / verified records ───────────────────────────────────
    if not _table_exists(bind, "oe_cc_asbuilt_record"):
        op.create_table(
            "oe_cc_asbuilt_record",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("record_number", sa.String(length=20), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("discipline", sa.String(length=50), nullable=True),
            sa.Column("location_description", sa.String(length=500), nullable=True),
            sa.Column("capture_method", sa.String(length=20), nullable=False, server_default="manual"),
            sa.Column("instrument", sa.String(length=255), nullable=True),
            sa.Column("instrument_calibration_ref", sa.String(length=120), nullable=True),
            sa.Column("accuracy_class", sa.String(length=20), nullable=False, server_default="standard"),
            sa.Column("accuracy_value", sa.String(length=80), nullable=True),
            sa.Column("accuracy_unit", sa.String(length=40), nullable=True),
            sa.Column("coordinate_system", sa.String(length=120), nullable=True),
            sa.Column("survey_date", sa.String(length=40), nullable=True),
            sa.Column("surveyed_by", sa.String(length=255), nullable=True),
            sa.Column("criterion_id", sa.String(length=36), nullable=True),
            sa.Column("measured_value", sa.String(length=80), nullable=True),
            sa.Column("deviation_value", sa.String(length=80), nullable=True),
            sa.Column("tolerance_result", sa.String(length=20), nullable=True),
            sa.Column("valid_for_legal_record", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("validity_signed_by", sa.String(length=36), nullable=True),
            sa.Column("validity_signed_at", sa.String(length=40), nullable=True),
            sa.Column("validity_signature_ip", sa.String(length=64), nullable=True),
            sa.Column("validity_signature_sha256", sa.String(length=64), nullable=True),
            sa.Column("source_kind", sa.String(length=30), nullable=False, server_default="manual"),
            sa.Column("source_ref", sa.String(length=36), nullable=True),
            sa.Column("deviation_map_uri", sa.String(length=2000), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
            sa.Column("raised_ncr_id", sa.String(length=36), nullable=True),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("project_id", "record_number", name="uq_oe_cc_asbuilt_project_number"),
        )

    # ── Indexes ──────────────────────────────────────────────────────────────
    for table, index_name, columns in _INDEXES:
        if _table_exists(bind, table) and not _index_exists(bind, table, index_name):
            op.create_index(index_name, table, columns)

    logger.info("v3193 construction_control as-built: 1 table + indexes ensured")


def downgrade() -> None:
    bind = op.get_bind()

    _drop_plan: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "oe_cc_asbuilt_record",
            (
                "ix_oe_cc_asbuilt_raised_ncr",
                "ix_oe_cc_asbuilt_source",
                "ix_oe_cc_asbuilt_criterion",
                "ix_oe_cc_asbuilt_project_status",
                "ix_oe_cc_asbuilt_project",
            ),
        ),
    )
    for table, indexes in _drop_plan:
        if _table_exists(bind, table):
            for index_name in indexes:
                if _index_exists(bind, table, index_name):
                    op.drop_index(index_name, table_name=table)
            op.drop_table(table)

    logger.info("v3193 construction_control as-built: reverted")
