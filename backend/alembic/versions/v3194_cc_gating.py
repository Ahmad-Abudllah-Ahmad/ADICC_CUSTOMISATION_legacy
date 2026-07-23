# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""construction_control Pillar 5: hold/witness/surveillance/review gating.

Adds the gating-engine table to the construction-control module:

* ``oe_cc_hold_gate`` - a gate attached to an activity, handover package or inspection.
  ``blocks_progress`` is the single source of truth for whether the gate stops work. A
  hold gate is a hard block and can never be waived; witness / surveillance / review gates
  default to soft and may be waived. Release is e-signed and the caller's party role must
  satisfy the gate's required party role.

Every operation is guarded so the migration is a safe no-op on a fresh install that
already booted the app (``Base.metadata.create_all`` builds the full current schema). The
downgrade fully reverses the upgrade.

Revision ID: v3194_cc_gating
Revises: v3193_cc_asbuilt
Create Date: 2026-06-22
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3194_cc_gating"
down_revision: Union[str, Sequence[str], None] = "v3193_cc_asbuilt"
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
    ("oe_cc_hold_gate", "ix_oe_cc_gate_project", ["project_id"]),
    ("oe_cc_hold_gate", "ix_oe_cc_gate_project_status", ["project_id", "status"]),
    ("oe_cc_hold_gate", "ix_oe_cc_gate_attached", ["attached_kind", "attached_id"]),
    ("oe_cc_hold_gate", "ix_oe_cc_gate_inspection", ["inspection_id"]),
)


def upgrade() -> None:
    bind = op.get_bind()

    # ── Table: hold/witness/surveillance/review gates ────────────────────────
    if not _table_exists(bind, "oe_cc_hold_gate"):
        op.create_table(
            "oe_cc_hold_gate",
            sa.Column("id", sa.String(length=36), primary_key=True),
            *_timestamps(),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("gate_number", sa.String(length=20), nullable=False),
            sa.Column("point_type", sa.String(length=20), nullable=False, server_default="hold"),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("required_party_role", sa.String(length=10), nullable=False, server_default="qa"),
            sa.Column("inspection_id", sa.String(length=36), nullable=True),
            sa.Column("criterion_id", sa.String(length=36), nullable=True),
            sa.Column("attached_kind", sa.String(length=20), nullable=True),
            sa.Column("attached_id", sa.String(length=36), nullable=True),
            sa.Column("blocks_progress", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("released_by", sa.String(length=36), nullable=True),
            sa.Column("released_party_role", sa.String(length=10), nullable=True),
            sa.Column("released_at", sa.String(length=40), nullable=True),
            sa.Column("release_justification", sa.Text(), nullable=True),
            sa.Column("release_signature_ip", sa.String(length=64), nullable=True),
            sa.Column("release_signature_sha256", sa.String(length=64), nullable=True),
            sa.Column("waived_by", sa.String(length=36), nullable=True),
            sa.Column("waived_reason", sa.Text(), nullable=True),
            sa.Column("approval_instance_id", sa.String(length=36), nullable=True),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("project_id", "gate_number", name="uq_oe_cc_gate_project_number"),
        )

    # ── Indexes ──────────────────────────────────────────────────────────────
    for table, index_name, columns in _INDEXES:
        if _table_exists(bind, table) and not _index_exists(bind, table, index_name):
            op.create_index(index_name, table, columns)

    logger.info("v3194 construction_control gating: 1 table + indexes ensured")


def downgrade() -> None:
    bind = op.get_bind()

    _drop_plan: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "oe_cc_hold_gate",
            (
                "ix_oe_cc_gate_inspection",
                "ix_oe_cc_gate_attached",
                "ix_oe_cc_gate_project_status",
                "ix_oe_cc_gate_project",
            ),
        ),
    )
    for table, indexes in _drop_plan:
        if _table_exists(bind, table):
            for index_name in indexes:
                if _index_exists(bind, table, index_name):
                    op.drop_index(index_name, table_name=table)
            op.drop_table(table)

    logger.info("v3194 construction_control gating: reverted")
