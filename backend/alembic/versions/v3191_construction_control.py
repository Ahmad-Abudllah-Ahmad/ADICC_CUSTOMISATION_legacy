# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""construction_control: universal QA/QC core schema (Pillar 1).

Adds the construction-control tables: acceptance criteria, inspections (with the
MIR/WIR/IR/hidden-works/acceptance type discriminator) and the shared Universal
Element Reference that links any control record to a model element regardless of
source format (IFC, RVT, DWG, DGN, ...).

New tables:

* ``oe_cc_acceptance_criterion`` - referenceable acceptance clause + tolerance +
  standard reference; every inspection result is judged against one of these.
* ``oe_cc_inspection`` - one inspection record with a type discriminator, a party
  role (qc/qa/tpi/ahj), a recorded pass/fail result and a link to the NCR auto-raised
  on failure.
* ``oe_cc_element_ref`` - the Universal Element Reference (UER): a polymorphic link
  resolving through the normalised bim_hub identity ``(model_id, stable_id)`` so IFC
  GlobalId is optional, never required.

Every operation is guarded with an inspector existence check (mirroring
``v3188_methodology_init``) so the migration is a safe no-op on a fresh install that
already booted the app (``Base.metadata.create_all`` builds the full current schema).
The downgrade fully reverses the upgrade.

Revision ID: v3191_construction_control
Revises: v3190_qms_signature_unique
Create Date: 2026-06-22
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3191_construction_control"
down_revision: Union[str, Sequence[str], None] = "v3190_qms_signature_unique"
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
    ("oe_cc_acceptance_criterion", "ix_oe_cc_criterion_project", ["project_id"]),
    ("oe_cc_acceptance_criterion", "ix_oe_cc_criterion_project_category", ["project_id", "category"]),
    ("oe_cc_inspection", "ix_oe_cc_inspection_project", ["project_id"]),
    ("oe_cc_inspection", "ix_oe_cc_inspection_project_status", ["project_id", "status"]),
    ("oe_cc_inspection", "ix_oe_cc_inspection_project_type", ["project_id", "inspection_type"]),
    ("oe_cc_inspection", "ix_oe_cc_inspection_criterion", ["criterion_id"]),
    ("oe_cc_inspection", "ix_oe_cc_inspection_raised_ncr", ["raised_ncr_id"]),
    ("oe_cc_element_ref", "ix_oe_cc_element_ref_owner", ["owner_type", "owner_id"]),
    ("oe_cc_element_ref", "ix_oe_cc_element_ref_model_stable", ["model_id", "stable_id"]),
    ("oe_cc_element_ref", "ix_oe_cc_element_ref_project", ["project_id"]),
    ("oe_cc_element_ref", "ix_oe_cc_element_ref_element", ["bim_element_id"]),
)


def upgrade() -> None:
    bind = op.get_bind()

    # ── Table 1: acceptance criteria ─────────────────────────────────────
    if not _table_exists(bind, "oe_cc_acceptance_criterion"):
        op.create_table(
            "oe_cc_acceptance_criterion",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("standard_ref", sa.String(length=120), nullable=True),
            sa.Column("discipline", sa.String(length=50), nullable=True),
            sa.Column("category", sa.String(length=80), nullable=True),
            sa.Column("characteristic", sa.String(length=255), nullable=True),
            sa.Column("method", sa.Text(), nullable=True),
            sa.Column("unit", sa.String(length=40), nullable=True),
            sa.Column("acceptance_rule", sa.String(length=20), nullable=False, server_default="text"),
            sa.Column("nominal_value", sa.String(length=80), nullable=True),
            sa.Column("tolerance_lower", sa.String(length=80), nullable=True),
            sa.Column("tolerance_upper", sa.String(length=80), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_cc_criterion_project_code"),
        )

    # ── Table 2: inspections ─────────────────────────────────────────────
    if not _table_exists(bind, "oe_cc_inspection"):
        op.create_table(
            "oe_cc_inspection",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("inspection_number", sa.String(length=20), nullable=False),
            sa.Column("inspection_type", sa.String(length=20), nullable=False),
            sa.Column("party_role", sa.String(length=10), nullable=False, server_default="qc"),
            sa.Column("intervention_point", sa.String(length=20), nullable=True),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("location_description", sa.String(length=500), nullable=True),
            sa.Column("activity_id", sa.String(length=36), nullable=True),
            sa.Column("criterion_id", sa.String(length=36), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
            sa.Column("result", sa.String(length=20), nullable=True),
            sa.Column("measured_value", sa.String(length=80), nullable=True),
            sa.Column("result_notes", sa.Text(), nullable=True),
            sa.Column("raised_ncr_id", sa.String(length=36), nullable=True),
            sa.Column("scheduled_at", sa.String(length=40), nullable=True),
            sa.Column("performed_at", sa.String(length=40), nullable=True),
            sa.Column("performed_by", sa.String(length=36), nullable=True),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("project_id", "inspection_number", name="uq_oe_cc_inspection_project_number"),
        )

    # ── Table 3: Universal Element Reference (shared, polymorphic) ───────
    if not _table_exists(bind, "oe_cc_element_ref"):
        op.create_table(
            "oe_cc_element_ref",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column("owner_type", sa.String(length=40), nullable=False),
            sa.Column("owner_id", sa.String(length=36), nullable=False),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "bim_element_id",
                sa.String(length=36),
                sa.ForeignKey("oe_bim_element.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "model_id",
                sa.String(length=36),
                sa.ForeignKey("oe_bim_model.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("stable_id", sa.String(length=255), nullable=True),
            sa.Column("source_format", sa.String(length=20), nullable=True),
            sa.Column("ifc_global_id", sa.String(length=22), nullable=True),
            sa.Column("native_id", sa.String(length=255), nullable=True),
            sa.Column("model_version", sa.String(length=20), nullable=True),
            sa.Column("element_name", sa.String(length=500), nullable=True),
            sa.Column("element_type", sa.String(length=100), nullable=True),
            sa.Column("bbox", sa.JSON(), nullable=True),
            sa.Column("viewpoint", sa.JSON(), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        )

    # ── Indexes ──────────────────────────────────────────────────────────
    for table, index_name, columns in _INDEXES:
        if _table_exists(bind, table) and not _index_exists(bind, table, index_name):
            op.create_index(index_name, table, columns)

    logger.info("v3191 construction_control: 3 tables + indexes ensured")


def downgrade() -> None:
    bind = op.get_bind()

    # Drop indexes then tables, in FK-safe (reverse) order.
    _drop_plan: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "oe_cc_element_ref",
            (
                "ix_oe_cc_element_ref_element",
                "ix_oe_cc_element_ref_project",
                "ix_oe_cc_element_ref_model_stable",
                "ix_oe_cc_element_ref_owner",
            ),
        ),
        (
            "oe_cc_inspection",
            (
                "ix_oe_cc_inspection_raised_ncr",
                "ix_oe_cc_inspection_criterion",
                "ix_oe_cc_inspection_project_type",
                "ix_oe_cc_inspection_project_status",
                "ix_oe_cc_inspection_project",
            ),
        ),
        (
            "oe_cc_acceptance_criterion",
            (
                "ix_oe_cc_criterion_project_category",
                "ix_oe_cc_criterion_project",
            ),
        ),
    )
    for table, indexes in _drop_plan:
        if _table_exists(bind, table):
            for index_name in indexes:
                if _index_exists(bind, table, index_name):
                    op.drop_index(index_name, table_name=table)
            op.drop_table(table)

    logger.info("v3191 construction_control: reverted")
