# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""methodology: estimating-methodology engine schema (Phase 2).

Adds the data-driven estimating-methodology tables that the pure cascade engine
(``app.modules.methodology.cascade``) computes against, plus the first-class
analytical dimensions, the position<->dimension-value link, the funding-source
master, and the additive methodology/dimension attribute columns on the existing
BOQ position.

New tables:

* ``oe_methodology`` - the country/industry template (hierarchy levels,
  dimension scheme, column preset, base/composite mapping, serialized cascade
  steps, VAT, currency/decimals).
* ``oe_analytic_dimension`` - an analytical dimension definition (tree or flat).
* ``oe_analytic_dimension_value`` - a value within a dimension
  (self-referencing ``parent_id`` for tree dimensions).
* ``oe_position_dimension_value`` - links a BOQ position to one value per
  dimension (unique on ``(position_id, dimension_id)``).
* ``oe_funding_source`` - funding-source master list.

Additive ``oe_boq_position`` columns (all nullable, ``server_default`` NULL):
``node_type``, ``contractor_id``, ``contract_id``, ``funding_source_id``,
``stage_id``.

Every operation is guarded with an inspector existence check (mirroring
``v3151_cost_spine``) so the migration is safe to re-run and is a no-op on a
fresh install that already booted the app (``Base.metadata.create_all`` builds
the full current schema). The downgrade fully reverses the upgrade so a stamp
roundtrip leaves the schema unchanged.

Revision ID: v3188_methodology_init
Revises: v3187_costs_mass_pricing
Create Date: 2026-06-18
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3188_methodology_init"
down_revision: Union[str, Sequence[str], None] = "v3187_costs_mass_pricing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def _table_exists(bind: sa.engine.Connection, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def _index_exists(bind: sa.engine.Connection, table: str, index: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(ix["name"] == index for ix in inspector.get_indexes(table))


def _column_exists(bind: sa.engine.Connection, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


# ── Additive BOQ-position columns: all String(36)/String(32), nullable ────────
_POSITION_COLUMNS: tuple[tuple[str, int], ...] = (
    ("node_type", 32),
    ("contractor_id", 36),
    ("contract_id", 36),
    ("funding_source_id", 36),
    ("stage_id", 36),
)


def upgrade() -> None:
    bind = op.get_bind()

    # ── Table 1: methodology templates ───────────────────────────────────
    if not _table_exists(bind, "oe_methodology"):
        op.create_table(
            "oe_methodology",
            sa.Column("id", sa.String(length=36), primary_key=True),
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
            sa.Column("slug", sa.String(length=80), nullable=False),
            sa.Column("scope", sa.String(length=20), nullable=False, server_default="builtin"),
            sa.Column("project_id", sa.String(length=36), nullable=True),
            sa.Column("country_code", sa.String(length=8), nullable=True),
            sa.Column("industry", sa.String(length=64), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("currency", sa.String(length=8), nullable=False, server_default=""),
            sa.Column("decimals", sa.Integer(), nullable=False, server_default="2"),
            sa.Column("hierarchy_levels", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("dimension_scheme", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("column_preset", sa.String(length=64), nullable=True),
            sa.Column("base_mapping", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("composites", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("cascade_steps", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("vat_rate", sa.String(length=50), nullable=True),
            sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("is_editable", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("slug", name="uq_methodology_slug"),
        )

    # ── Table 2: analytical dimensions ───────────────────────────────────
    if not _table_exists(bind, "oe_analytic_dimension"):
        op.create_table(
            "oe_analytic_dimension",
            sa.Column("id", sa.String(length=36), primary_key=True),
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
            sa.Column("project_id", sa.String(length=36), nullable=True),
            sa.Column("methodology_slug", sa.String(length=80), nullable=True),
            sa.Column("key", sa.String(length=80), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=False),
            sa.Column("kind", sa.String(length=20), nullable=False, server_default="flat"),
            sa.Column("is_required", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        )

    # ── Table 3: analytical-dimension values (self-referencing tree) ─────
    if not _table_exists(bind, "oe_analytic_dimension_value"):
        op.create_table(
            "oe_analytic_dimension_value",
            sa.Column("id", sa.String(length=36), primary_key=True),
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
                "dimension_id",
                sa.String(length=36),
                sa.ForeignKey("oe_analytic_dimension.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "parent_id",
                sa.String(length=36),
                sa.ForeignKey("oe_analytic_dimension_value.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        )

    # ── Table 4: position <-> dimension-value link ───────────────────────
    if not _table_exists(bind, "oe_position_dimension_value"):
        op.create_table(
            "oe_position_dimension_value",
            sa.Column("id", sa.String(length=36), primary_key=True),
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
            # Cross-module reference to oe_boq_position (plain string, no FK).
            sa.Column("position_id", sa.String(length=36), nullable=False),
            sa.Column(
                "dimension_id",
                sa.String(length=36),
                sa.ForeignKey("oe_analytic_dimension.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "value_id",
                sa.String(length=36),
                sa.ForeignKey("oe_analytic_dimension_value.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "position_id",
                "dimension_id",
                name="uq_position_dimension_value_position_dimension",
            ),
        )

    # ── Table 5: funding-source master ───────────────────────────────────
    if not _table_exists(bind, "oe_funding_source"):
        op.create_table(
            "oe_funding_source",
            sa.Column("id", sa.String(length=36), primary_key=True),
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
            sa.Column("project_id", sa.String(length=36), nullable=True),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        )

    # ── Indexes on the new tables ────────────────────────────────────────
    _new_indexes: tuple[tuple[str, str, list[str]], ...] = (
        ("oe_methodology", "ix_methodology_slug", ["slug"]),
        ("oe_methodology", "ix_methodology_scope_country", ["scope", "country_code"]),
        ("oe_methodology", "ix_methodology_project_id", ["project_id"]),
        ("oe_analytic_dimension", "ix_analytic_dimension_project_id", ["project_id"]),
        ("oe_analytic_dimension", "ix_analytic_dimension_methodology", ["methodology_slug"]),
        ("oe_analytic_dimension_value", "ix_analytic_dim_value_dimension", ["dimension_id"]),
        ("oe_analytic_dimension_value", "ix_analytic_dim_value_parent", ["parent_id"]),
        ("oe_position_dimension_value", "ix_position_dimension_value_position", ["position_id"]),
        ("oe_position_dimension_value", "ix_position_dimension_value_dimension", ["dimension_id"]),
        ("oe_position_dimension_value", "ix_position_dimension_value_value", ["value_id"]),
        ("oe_funding_source", "ix_funding_source_project_id", ["project_id"]),
    )
    for table, index_name, columns in _new_indexes:
        if not _index_exists(bind, table, index_name):
            op.create_index(index_name, table, columns)

    # ── Additive nullable BOQ-position columns ───────────────────────────
    for column, length in _POSITION_COLUMNS:
        if not _column_exists(bind, "oe_boq_position", column):
            op.add_column(
                "oe_boq_position",
                sa.Column(column, sa.String(length=length), nullable=True),
            )

    logger.info("v3188 methodology_init: 5 tables + indexes + 5 oe_boq_position columns ensured")


def downgrade() -> None:
    bind = op.get_bind()

    # ── Additive BOQ-position columns ────────────────────────────────────
    for column, _length in _POSITION_COLUMNS:
        if _column_exists(bind, "oe_boq_position", column):
            # SQLite cannot DROP COLUMN without a table rebuild; batch handles it.
            with op.batch_alter_table("oe_boq_position") as batch:
                batch.drop_column(column)

    # ── Drop tables in FK-safe (reverse) order, indexes first ────────────
    _drop_plan: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "oe_position_dimension_value",
            (
                "ix_position_dimension_value_value",
                "ix_position_dimension_value_dimension",
                "ix_position_dimension_value_position",
            ),
        ),
        (
            "oe_analytic_dimension_value",
            (
                "ix_analytic_dim_value_parent",
                "ix_analytic_dim_value_dimension",
            ),
        ),
        (
            "oe_analytic_dimension",
            (
                "ix_analytic_dimension_methodology",
                "ix_analytic_dimension_project_id",
            ),
        ),
        (
            "oe_funding_source",
            ("ix_funding_source_project_id",),
        ),
        (
            "oe_methodology",
            (
                "ix_methodology_project_id",
                "ix_methodology_scope_country",
                "ix_methodology_slug",
            ),
        ),
    )
    for table, indexes in _drop_plan:
        if _table_exists(bind, table):
            for index_name in indexes:
                if _index_exists(bind, table, index_name):
                    op.drop_index(index_name, table_name=table)
            op.drop_table(table)

    logger.info("v3188 methodology_init: reverted")
