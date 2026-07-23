# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""construction_control Pillar 4: handover / acceptance package.

Adds the handover-package table to the construction-control module:

* ``oe_cc_handover_package`` - the completion-regime wrapper that auto-assembles the
  acceptance evidence (passed inspections, recorded as-builts, accepted materials, lab
  tests) into a manifest, computes a completion gate from the open NCRs and the
  unreleased blocking hold gates on the project, and issues a regime-specific acceptance
  certificate. A certificate is issued only once the gate is clear or a manager overrides
  it (recorded as a documentation NCR); the issue is captured with an e-signature.

The package links optional model elements through the shared Universal Element Reference
(``oe_cc_element_ref`` from v3191) via the polymorphic ``owner_type`` value
``handover_package`` - no schema change there. Every operation is guarded so the
migration is a safe no-op on a fresh install that already booted the app
(``Base.metadata.create_all`` builds the full current schema). The downgrade fully
reverses the upgrade.

Revision ID: v3195_cc_handover
Revises: v3194_cc_gating
Create Date: 2026-06-22
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3195_cc_handover"
down_revision: Union[str, Sequence[str], None] = "v3194_cc_gating"
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
    ("oe_cc_handover_package", "ix_oe_cc_handover_project", ["project_id"]),
    ("oe_cc_handover_package", "ix_oe_cc_handover_project_status", ["project_id", "status"]),
    ("oe_cc_handover_package", "ix_oe_cc_handover_closeout", ["closeout_package_id"]),
)


def upgrade() -> None:
    bind = op.get_bind()

    # ── Table: handover / acceptance packages ────────────────────────────────
    if not _table_exists(bind, "oe_cc_handover_package"):
        op.create_table(
            "oe_cc_handover_package",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("package_number", sa.String(length=20), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("completion_regime", sa.String(length=20), nullable=False, server_default="taking_over"),
            sa.Column("completion_type", sa.String(length=20), nullable=False, server_default="whole"),
            sa.Column("section_ref", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
            sa.Column("gating_state", sa.String(length=20), nullable=False, server_default="blocked"),
            sa.Column("open_ncr_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("unreleased_hold_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("completeness_pct", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("gating_override_by", sa.String(length=36), nullable=True),
            sa.Column("gating_override_reason", sa.Text(), nullable=True),
            sa.Column("certificate_no", sa.String(length=120), nullable=True),
            sa.Column("issued_at", sa.String(length=40), nullable=True),
            sa.Column("issued_by", sa.String(length=36), nullable=True),
            sa.Column("issue_signature_ip", sa.String(length=64), nullable=True),
            sa.Column("issue_signature_sha256", sa.String(length=64), nullable=True),
            sa.Column("closeout_package_id", sa.String(length=36), nullable=True),
            sa.Column("dossier_key", sa.String(length=2000), nullable=True),
            sa.Column("dossier_built_at", sa.String(length=40), nullable=True),
            sa.Column("assembled_at", sa.String(length=40), nullable=True),
            sa.Column("approval_instance_id", sa.String(length=36), nullable=True),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("project_id", "package_number", name="uq_oe_cc_handover_project_number"),
        )

    # ── Indexes ──────────────────────────────────────────────────────────────
    for table, index_name, columns in _INDEXES:
        if _table_exists(bind, table) and not _index_exists(bind, table, index_name):
            op.create_index(index_name, table, columns)

    logger.info("v3195 construction_control handover: 1 table + indexes ensured")


def downgrade() -> None:
    bind = op.get_bind()

    _drop_plan: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "oe_cc_handover_package",
            (
                "ix_oe_cc_handover_closeout",
                "ix_oe_cc_handover_project_status",
                "ix_oe_cc_handover_project",
            ),
        ),
    )
    for table, indexes in _drop_plan:
        if _table_exists(bind, table):
            for index_name in indexes:
                if _index_exists(bind, table, index_name):
                    op.drop_index(index_name, table_name=table)
            op.drop_table(table)

    logger.info("v3195 construction_control handover: reverted")
