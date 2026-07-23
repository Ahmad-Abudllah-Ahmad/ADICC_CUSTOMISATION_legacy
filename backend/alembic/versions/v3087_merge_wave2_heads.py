"""v3087 — merge Wave 2 sibling heads (procurement / tendering / hse).

Wave 2 of the v3.11 improvement campaign produced three independent
migrations off ``v3083_merge_v311_heads``:

* ``v3084_procurement_scorecard_indices`` — supplier scorecard indices.
* ``v3085_tendering_addendum_leveling`` — addenda + bid leveling.
* ``v3086_hse_osha_corrective_fsm`` — OSHA 300 + CAPA FSM.

This revision is a no-op merge that consolidates the three back into a
single head so subsequent waves can chain off one well-known parent.

Revision ID: v3087_merge_wave2_heads
Revises: v3084_procurement_scorecard_indices, v3085_tendering_addendum_leveling, v3086_hse_osha_corrective_fsm
Create Date: 2026-05-20
"""

from __future__ import annotations

from typing import Sequence, Union

revision: str = "v3087_merge_wave2_heads"
down_revision: Union[str, Sequence[str], None] = (
    "v3084_procurement_scorecard_indices",
    "v3085_tendering_addendum_leveling",
    "v3086_hse_osha_corrective_fsm",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op — merge point only."""


def downgrade() -> None:
    """No-op — merge point only."""
