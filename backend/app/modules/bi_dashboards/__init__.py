# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""BI Dashboards & Reporting - Module 20 (Wave 4).

Read-only across the platform. Owns KPI definitions, dashboard configs,
widget configs, report definitions, schedules, alert rules, saved
filters, and snapshot caches. Reads from every other module's tables
via the registered formula functions in :mod:`.kpis`.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions + KPI registry + subscribers."""
    from app.modules.bi_dashboards import kpis as _kpis  # noqa: F401
    from app.modules.bi_dashboards.events import register_subscribers
    from app.modules.bi_dashboards.permissions import (
        register_bi_dashboards_permissions,
    )

    register_bi_dashboards_permissions()
    register_subscribers()
