# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""progress: percent-complete + planned S-curve tables.

Two tables for the new Progress module (deep-improve wave,
task #183 — Snags+Punchlist+Progress):

* ``oe_progress_entry`` — append-only percent-complete observations per
                          BOQ position (optional BOQ link for project-level
                          entries). NUMERIC(6,3) with CHECK constraint
                          guarantees range [0, 100].  Optional geo pin
                          (lat/lon) captured by the field worker.
* ``oe_progress_plan``  — planned S-curve points per project (per period).

Idempotent. Fresh installs that boot the app first will already have
these tables from ``Base.metadata.create_all`` — running this migration
afterwards is a no-op. Every NOT NULL column carries a ``server_default``
so the ``create_all`` path works too.

Revision ID: v3139_progress_init
Revises: v3138_moc_init
Create Date: 2026-05-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3139_progress_init"
down_revision: Union[str, Sequence[str], None] = "v3138_moc_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENTRY = "oe_progress_entry"
_PLAN = "oe_progress_plan"


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── oe_progress_entry ─────────────────────────────────────────────
    if not _has_table(inspector, _ENTRY):
        op.create_table(
            _ENTRY,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "project_id",
                sa.String(36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "boq_position_id",
                sa.String(36),
                sa.ForeignKey("oe_boq_position.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("period_label", sa.String(20), nullable=False, server_default=""),
            sa.Column(
                "percent_complete",
                sa.Numeric(6, 3),
                nullable=False,
                server_default="0",
            ),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("recorded_by", sa.String(36), nullable=True),
            sa.Column(
                "recorded_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("geo_lat", sa.Numeric(10, 7), nullable=True),
            sa.Column("geo_lon", sa.Numeric(10, 7), nullable=True),
            sa.Column("photos", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.CheckConstraint(
                "percent_complete >= 0 AND percent_complete <= 100",
                name="ck_progress_entry_pct_range",
            ),
            sa.CheckConstraint(
                "geo_lat IS NULL OR (geo_lat >= -90 AND geo_lat <= 90)",
                name="ck_progress_entry_lat_range",
            ),
            sa.CheckConstraint(
                "geo_lon IS NULL OR (geo_lon >= -180 AND geo_lon <= 180)",
                name="ck_progress_entry_lon_range",
            ),
        )
        op.create_index(f"ix_{_ENTRY}_project_id", _ENTRY, ["project_id"])
        op.create_index(f"ix_{_ENTRY}_boq_position_id", _ENTRY, ["boq_position_id"])
        op.create_index(
            "ix_progress_entry_position_recorded",
            _ENTRY,
            ["boq_position_id", "recorded_at"],
        )
        op.create_index(
            "ix_progress_entry_project_recorded",
            _ENTRY,
            ["project_id", "recorded_at"],
        )

    # ── oe_progress_plan ──────────────────────────────────────────────
    if not _has_table(inspector, _PLAN):
        op.create_table(
            _PLAN,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "project_id",
                sa.String(36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("period_label", sa.String(20), nullable=False, server_default=""),
            sa.Column(
                "planned_pct",
                sa.Numeric(6, 3),
                nullable=False,
                server_default="0",
            ),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.CheckConstraint(
                "planned_pct >= 0 AND planned_pct <= 100",
                name="ck_progress_plan_pct_range",
            ),
        )
        op.create_index(f"ix_{_PLAN}_project_id", _PLAN, ["project_id"])
        op.create_index(
            "ix_progress_plan_project_period",
            _PLAN,
            ["project_id", "period_label"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, _PLAN):
        op.drop_index("ix_progress_plan_project_period", table_name=_PLAN)
        op.drop_index(f"ix_{_PLAN}_project_id", table_name=_PLAN)
        op.drop_table(_PLAN)

    if _has_table(inspector, _ENTRY):
        op.drop_index("ix_progress_entry_project_recorded", table_name=_ENTRY)
        op.drop_index("ix_progress_entry_position_recorded", table_name=_ENTRY)
        op.drop_index(f"ix_{_ENTRY}_boq_position_id", table_name=_ENTRY)
        op.drop_index(f"ix_{_ENTRY}_project_id", table_name=_ENTRY)
        op.drop_table(_ENTRY)
