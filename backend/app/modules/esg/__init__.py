# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""ESG Site Performance module.

Operational site ESG metrics (energy, water, waste, on-site CO2e, local labour,
training, safety and governance) recorded per reporting period against targets,
with direction-aware KPI cards and short trends. Distinct from embodied carbon,
which lives in the carbon / 6D module.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions."""
    from app.modules.esg.permissions import register_esg_permissions

    register_esg_permissions()
