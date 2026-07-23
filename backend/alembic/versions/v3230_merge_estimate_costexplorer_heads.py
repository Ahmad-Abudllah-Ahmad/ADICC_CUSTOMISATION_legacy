# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Merge the two open alembic heads into one.

The estimating wave (``v3200_estimate_modules``) branched from the four heads
that parallel work had left open, but not from
``v3221_cost_explorer_reverse_index`` (the Cost Explorer reverse-index
revision, which ran on its own line through ``v3220_field_time_timesheets``).
That left the history with two heads, so a plain ``alembic upgrade head`` or
``alembic stamp head`` fails with "Multiple heads are present" on an external
PostgreSQL deployment (seen during the v10.7.0 production cutover).

This is a pure merge point: no schema change, it only rejoins the two lineages
so the history has a single unambiguous head again. The embedded runtime that
builds its schema through ``create_all`` is unaffected either way.

Revision ID: v3230_merge_estimate_costexplorer_heads
Revises: v3200_estimate_modules, v3221_cost_explorer_reverse_index
Create Date: 2026-07-08
"""

from __future__ import annotations

revision = "v3230_merge_estimate_costexplorer_heads"
down_revision = (
    "v3200_estimate_modules",
    "v3221_cost_explorer_reverse_index",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op: this revision only merges two heads, it changes no schema."""


def downgrade() -> None:
    """No-op: re-splitting a merge point back into two heads is not supported."""
