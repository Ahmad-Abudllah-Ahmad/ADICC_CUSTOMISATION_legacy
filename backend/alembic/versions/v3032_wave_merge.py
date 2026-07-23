"""Merge parallel deep-wave heads into single head.

Five DEEP-wave sub-agents ran in parallel (A/B/C/D/E + CRS + size_limits
+ stability) and each created its own additive migration. The resulting
chain has three terminal heads:

  * v3027_supplier_catalogs_bi_extensions  (Wave E)
  * v3028_portal_email_optin                (Wave A)
  * v3031_crs_detection                     (CRS detector chain — pulls
                                              v3027_service_ticket_source →
                                              v3028_crm_hierarchy_carbon_grid →
                                              v3029_qms_calibration_template_hse_extras →
                                              v3030_module4_extras)

This merge revision unifies them so ``alembic upgrade head`` operates on a
single head. No schema changes — pure merge marker.
"""

from __future__ import annotations

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "v3032_wave_merge"
down_revision: Union[str, Sequence[str], None] = (
    "v3027_supplier_catalogs_bi_extensions",
    "v3028_portal_email_optin",
    "v3031_crs_detection",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op merge — schema changes already applied by parent revisions."""
    pass


def downgrade() -> None:
    """No-op — splitting back into three heads is not meaningful."""
    pass
