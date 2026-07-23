# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""construction_control Pillar 2: material records (digital passport) + test results.

Adds the materials/digital-passport tables to the construction-control module:

* ``oe_cc_material_record`` - the digital material passport: an EN 10204 certificate
  grade (2.1 / 2.2 / 3.1 / 3.2), CE/UKCA + Declaration of Performance markings,
  batch/heat/lot traceability and certificate validity, optionally tied to a
  procurement goods receipt. A rejected review raises a material NCR automatically.
* ``oe_cc_test_result`` - a material or field test result judged against an acceptance
  criterion (sample id, method, ISO/IEC 17025 lab accreditation). A failed result
  raises an NCR, mirroring the inspection fail -> NCR bridge.

Both reuse the shared Universal Element Reference (``oe_cc_element_ref`` from v3191) via
the polymorphic ``owner_type`` values ``material_record`` / ``test_result`` - no schema
change there. Every operation is guarded so the migration is a safe no-op on a fresh
install that already booted the app (``Base.metadata.create_all`` builds the full current
schema). The downgrade fully reverses the upgrade.

Revision ID: v3192_cc_materials_test_results
Revises: v3191_construction_control
Create Date: 2026-06-22
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3192_cc_materials_test_results"
down_revision: Union[str, Sequence[str], None] = "v3191_construction_control"
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
    ("oe_cc_material_record", "ix_oe_cc_material_project", ["project_id"]),
    ("oe_cc_material_record", "ix_oe_cc_material_project_status", ["project_id", "status"]),
    ("oe_cc_material_record", "ix_oe_cc_material_project_type", ["project_id", "material_type"]),
    ("oe_cc_material_record", "ix_oe_cc_material_gr", ["gr_id"]),
    ("oe_cc_material_record", "ix_oe_cc_material_criterion", ["criterion_id"]),
    ("oe_cc_material_record", "ix_oe_cc_material_raised_ncr", ["raised_ncr_id"]),
    ("oe_cc_test_result", "ix_oe_cc_test_project", ["project_id"]),
    ("oe_cc_test_result", "ix_oe_cc_test_project_status", ["project_id", "status"]),
    ("oe_cc_test_result", "ix_oe_cc_test_material", ["material_record_id"]),
    ("oe_cc_test_result", "ix_oe_cc_test_criterion", ["criterion_id"]),
    ("oe_cc_test_result", "ix_oe_cc_test_raised_ncr", ["raised_ncr_id"]),
)


def upgrade() -> None:
    bind = op.get_bind()

    # ── Table 1: material records (digital passport) ─────────────────────────
    if not _table_exists(bind, "oe_cc_material_record"):
        op.create_table(
            "oe_cc_material_record",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("record_number", sa.String(length=20), nullable=False),
            sa.Column("name", sa.String(length=500), nullable=False),
            sa.Column("material_type", sa.String(length=80), nullable=True),
            sa.Column("spec_grade", sa.String(length=255), nullable=True),
            sa.Column("manufacturer", sa.String(length=255), nullable=True),
            sa.Column("supplier", sa.String(length=255), nullable=True),
            sa.Column("supplier_id", sa.String(length=36), nullable=True),
            sa.Column("product_code", sa.String(length=255), nullable=True),
            sa.Column("cert_type", sa.String(length=20), nullable=True),
            sa.Column("cert_number", sa.String(length=120), nullable=True),
            sa.Column("cert_issuer", sa.String(length=255), nullable=True),
            sa.Column("cert_document_id", sa.String(length=36), nullable=True),
            sa.Column("dop_number", sa.String(length=120), nullable=True),
            sa.Column("ce_marking", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("ukca_marking", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("issued_at", sa.String(length=40), nullable=True),
            sa.Column("valid_from", sa.String(length=40), nullable=True),
            sa.Column("valid_until", sa.String(length=40), nullable=True),
            sa.Column("batch_number", sa.String(length=120), nullable=True),
            sa.Column("heat_number", sa.String(length=120), nullable=True),
            sa.Column("lot_number", sa.String(length=120), nullable=True),
            sa.Column("quantity", sa.String(length=80), nullable=True),
            sa.Column("unit", sa.String(length=40), nullable=True),
            sa.Column("criterion_id", sa.String(length=36), nullable=True),
            sa.Column("po_id", sa.String(length=36), nullable=True),
            sa.Column("gr_id", sa.String(length=36), nullable=True),
            sa.Column("gr_item_id", sa.String(length=36), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
            sa.Column("review_notes", sa.Text(), nullable=True),
            sa.Column("raised_ncr_id", sa.String(length=36), nullable=True),
            sa.Column("received_at", sa.String(length=40), nullable=True),
            sa.Column("received_by", sa.String(length=36), nullable=True),
            sa.Column("reviewed_at", sa.String(length=40), nullable=True),
            sa.Column("reviewed_by", sa.String(length=36), nullable=True),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("project_id", "record_number", name="uq_oe_cc_material_project_number"),
        )

    # ── Table 2: test results (ISO/IEC 17025) ────────────────────────────────
    if not _table_exists(bind, "oe_cc_test_result"):
        op.create_table(
            "oe_cc_test_result",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("result_number", sa.String(length=20), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("material_record_id", sa.String(length=36), nullable=True),
            sa.Column("inspection_id", sa.String(length=36), nullable=True),
            sa.Column("criterion_id", sa.String(length=36), nullable=True),
            sa.Column("sample_id", sa.String(length=120), nullable=True),
            sa.Column("test_method", sa.String(length=255), nullable=True),
            sa.Column("lab_name", sa.String(length=255), nullable=True),
            sa.Column("lab_accreditation", sa.String(length=120), nullable=True),
            sa.Column("is_accredited", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("measured_value", sa.String(length=80), nullable=True),
            sa.Column("unit", sa.String(length=40), nullable=True),
            sa.Column("specimen_age_days", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
            sa.Column("result", sa.String(length=20), nullable=True),
            sa.Column("result_notes", sa.Text(), nullable=True),
            sa.Column("raised_ncr_id", sa.String(length=36), nullable=True),
            sa.Column("sampled_at", sa.String(length=40), nullable=True),
            sa.Column("tested_at", sa.String(length=40), nullable=True),
            sa.Column("performed_by", sa.String(length=36), nullable=True),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("project_id", "result_number", name="uq_oe_cc_test_project_number"),
        )

    # ── Indexes ──────────────────────────────────────────────────────────────
    for table, index_name, columns in _INDEXES:
        if _table_exists(bind, table) and not _index_exists(bind, table, index_name):
            op.create_index(index_name, table, columns)

    logger.info("v3192 construction_control materials/tests: 2 tables + indexes ensured")


def downgrade() -> None:
    bind = op.get_bind()

    _drop_plan: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "oe_cc_test_result",
            (
                "ix_oe_cc_test_raised_ncr",
                "ix_oe_cc_test_criterion",
                "ix_oe_cc_test_material",
                "ix_oe_cc_test_project_status",
                "ix_oe_cc_test_project",
            ),
        ),
        (
            "oe_cc_material_record",
            (
                "ix_oe_cc_material_raised_ncr",
                "ix_oe_cc_material_criterion",
                "ix_oe_cc_material_gr",
                "ix_oe_cc_material_project_type",
                "ix_oe_cc_material_project_status",
                "ix_oe_cc_material_project",
            ),
        ),
    )
    for table, indexes in _drop_plan:
        if _table_exists(bind, table):
            for index_name in indexes:
                if _index_exists(bind, table, index_name):
                    op.drop_index(index_name, table_name=table)
            op.drop_table(table)

    logger.info("v3192 construction_control materials/tests: reverted")
