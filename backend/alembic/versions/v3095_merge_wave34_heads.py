"""v3095 — merge Wave 3 + Wave 4 sibling heads.

After Wave 3 (meetings / erpchat / notifications) and Wave 4 background
agents (T10-T13) landed in parallel, seven independent migrations
branched off ``v3087_merge_wave2_heads``:

Wave 3:
* ``v3088_meetings_recurring_attendance`` — recurring meetings + attendance.
* ``v3089_erpchat_feedback`` — ERP chat feedback.
* ``v3090_notification_preferences`` — per-user notification preferences.

Wave 4:
* ``v3091_service_sla_recurring`` — service SLA + recurring tickets (T10).
* ``v3092_bi_crossfilter`` — BI dashboards cross-filter state (T11).
* ``v3093_subs_prequal_insurance`` — subcontractor prequal + insurance (T12).
* ``v3094_requirement_deliverables`` — requirement deliverables (T13).

This revision is a no-op merge that consolidates the seven back into a
single head so subsequent waves can chain off one well-known parent.

Revision ID: v3095_merge_wave34_heads
Revises: v3088_meetings_recurring_attendance, v3089_erpchat_feedback, v3090_notification_preferences, v3091_service_sla_recurring, v3092_bi_crossfilter, v3093_subs_prequal_insurance, v3094_requirement_deliverables
Create Date: 2026-05-20
"""

from __future__ import annotations

from typing import Sequence, Union

revision: str = "v3095_merge_wave34_heads"
down_revision: Union[str, Sequence[str], None] = (
    "v3088_meetings_recurring_attendance",
    "v3089_erpchat_feedback",
    "v3090_notification_preferences",
    "v3091_service_sla_recurring",
    "v3092_bi_crossfilter",
    "v3093_subs_prequal_insurance",
    "v3094_requirement_deliverables",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op — merge point only."""


def downgrade() -> None:
    """No-op — merge point only."""
