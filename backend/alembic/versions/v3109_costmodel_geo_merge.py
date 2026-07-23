# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""merge — unite cross-module geo + costmodel idempotency branches.

R6.5 wave-2 produced two independent migrations off
``v3106_geo_hub_init`` because they were authored in parallel
worktrees:

* ``v3107_cross_module_geo_binding`` — adds nullable ``geo_lat`` /
  ``geo_lon`` columns to ``oe_safety_incident`` and
  ``oe_punchlist_item`` so HSE pins and Punchlist pins can render on
  the geo hub map.
* ``v3107_costmodel_budget_line_idempotency`` + its child
  ``v3108_costmodel_snapshot_period_unique`` — adds idempotency guards
  to ``oe_costmodel_budget_line`` (re-running boq→budget no longer
  doubles BAC) and ``(project_id, period)`` uniqueness to snapshots.

Both branches are strictly additive and inspector-guarded so this
merge is a no-op on schema state. Required only so the alembic head
stays single — the seed snapshot is happy either way.
"""

from __future__ import annotations

# Revision identifiers, used by Alembic.
revision: str = "v3109_costmodel_geo_merge"
down_revision: tuple[str, str] = (
    "v3107_cross_module_geo_binding",
    "v3108_costmodel_snapshot_unique",
)
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    """No-op merge — both parent branches are additive + inspector-guarded."""


def downgrade() -> None:
    """No-op merge — see ``upgrade``."""
