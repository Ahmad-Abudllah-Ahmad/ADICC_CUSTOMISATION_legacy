# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Project Controls - executive cross-module controls dashboard (feature 09).

Read-only across the platform. Assembles the cost + schedule + quality +
safety + risk + change spine for one project (or the portfolio) in a single
round-trip, status-banded, with cross-module drill-down deep links. Sits on
top of the shared :mod:`app.modules.bi_dashboards.kpis` registry.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions."""
    from app.modules.project_controls.permissions import (
        register_project_controls_permissions,
    )

    register_project_controls_permissions()
