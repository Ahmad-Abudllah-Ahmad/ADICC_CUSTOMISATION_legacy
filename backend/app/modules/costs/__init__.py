# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Cost Database module.

Provides cost item management, rate databases (CWICR, regional cost indices),
search, and bulk import functionality.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions."""
    from app.modules.costs.permissions import register_cost_permissions

    register_cost_permissions()
