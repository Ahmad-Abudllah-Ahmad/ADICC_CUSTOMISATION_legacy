# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""money: schema-level float→Decimal sweep (v3 §10) — no DB column changes.

This revision is the alembic anchor for the schema-side conversion of
~111 Pydantic money fields (the deferred set catalogued in
``docs/MONEY_FLOAT_REMAINING.md``) from ``float`` to ``Decimal`` with a
``@field_serializer(..., when_used='json')`` that returns
``_serialise_money(v)`` so the wire format is the v3 §10 contract:
*money is JSON-string, not JSON-number*.

No DDL change is required because every model in the swept scope
(``assemblies`` / ``catalog`` / ``costmodel`` / ``risk`` /
``schedule.WorkOrder`` / ``finance`` rollups / ``tendering`` /
``clash_*`` / ``coordination_hub`` aggregates / ``boq.PrerequisiteItem``
ad-hoc rows / ``ai`` job blobs) already stores money values as ``String``
or ``Float`` (legacy parity) — only the *wire* contract changes. The
migration is kept as a chain-extending no-op so:

* fresh-install ``alembic upgrade head`` advances cleanly past this rev;
* the ``alembic_head_matches`` health probe stays green;
* the next migration in the chain can ``Revises = v3129_money_decimal_sweep``
  without ambiguity.

If a future audit converts one of the still-Float DB columns
(``ai.cost_usd_estimate``, ``clash_ai_triage.cost_usd_estimate``) to
``Numeric``, that DDL belongs in its OWN revision so the rollback story
is one feature per revision — not buried inside this anchor.

Revision ID: v3129_money_decimal_sweep
Revises: v3128_ai_estimate_cost_usd
Create Date: 2026-05-24
"""

from __future__ import annotations

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "v3129_money_decimal_sweep"
down_revision: Union[str, Sequence[str], None] = "v3128_ai_estimate_cost_usd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No DDL — wire-only contract change. See module docstring."""


def downgrade() -> None:
    """No DDL — wire-only contract change. See module docstring."""
