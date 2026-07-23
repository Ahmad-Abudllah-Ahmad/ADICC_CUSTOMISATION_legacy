# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""BI Dashboards: cross-filter + drill-path columns.

Wave 4 / T11 — gives the BI dashboards module Power BI-style cross-filter
behaviour. Two strictly-additive columns:

* ``oe_bi_dashboards_dashboard.cross_filter_enabled`` (Boolean, default False):
  opt-in flag — when False (the default for every existing row) the dashboard
  ignores any filter dict supplied by a caller, preserving the v3.x static
  behaviour byte-for-byte. When True, the dashboard's evaluate endpoint
  propagates the filter dict into every widget's KPI query.

* ``oe_bi_dashboards_widget.drill_path`` (JSON, nullable, default NULL):
  describes how a click on this widget propagates a filter to the rest of
  the dashboard, e.g. ``{"filter_field": "project_id",
  "filter_value_from": "row.project_id"}``. NULL means the widget is not
  clickable for cross-filter purposes.

Idempotent — inspector-guarded so re-runs on a partially-migrated DB skip
columns already present. SQLite-safe (Boolean defaults to text "0", JSON
column type cleanly maps to TEXT under SQLite).

Revision ID: v3092_bi_crossfilter
Revises: v3087_merge_wave2_heads
Create Date: 2026-05-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3092_bi_crossfilter"
down_revision: Union[str, Sequence[str], None] = "v3087_merge_wave2_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DASHBOARD_TABLE = "oe_bi_dashboards_dashboard"
_WIDGET_TABLE = "oe_bi_dashboards_widget"


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _existing_cols(inspector: sa.engine.reflection.Inspector, table: str) -> set[str]:
    if not _has_table(inspector, table):
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    """Add ``cross_filter_enabled`` to dashboards and ``drill_path`` to widgets."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── oe_bi_dashboards_dashboard.cross_filter_enabled ──────────────────
    if _has_table(inspector, _DASHBOARD_TABLE):
        dash_cols = _existing_cols(inspector, _DASHBOARD_TABLE)
        if "cross_filter_enabled" not in dash_cols:
            # ``batch_alter_table`` keeps SQLite happy. The default is False —
            # every existing dashboard keeps its static-render behaviour until
            # an owner opts in via a PATCH.
            with op.batch_alter_table(_DASHBOARD_TABLE) as batch:
                batch.add_column(
                    sa.Column(
                        "cross_filter_enabled",
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.false(),
                    ),
                )

    # ── oe_bi_dashboards_widget.drill_path ───────────────────────────────
    if _has_table(inspector, _WIDGET_TABLE):
        widget_cols = _existing_cols(inspector, _WIDGET_TABLE)
        if "drill_path" not in widget_cols:
            with op.batch_alter_table(_WIDGET_TABLE) as batch:
                batch.add_column(
                    sa.Column(
                        "drill_path",
                        sa.JSON(),
                        nullable=True,
                        server_default=None,
                    ),
                )


def downgrade() -> None:
    """Drop ``cross_filter_enabled`` and ``drill_path`` if present."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, _WIDGET_TABLE):
        widget_cols = _existing_cols(inspector, _WIDGET_TABLE)
        if "drill_path" in widget_cols:
            with op.batch_alter_table(_WIDGET_TABLE) as batch:
                batch.drop_column("drill_path")

    if _has_table(inspector, _DASHBOARD_TABLE):
        dash_cols = _existing_cols(inspector, _DASHBOARD_TABLE)
        if "cross_filter_enabled" in dash_cols:
            with op.batch_alter_table(_DASHBOARD_TABLE) as batch:
                batch.drop_column("cross_filter_enabled")
