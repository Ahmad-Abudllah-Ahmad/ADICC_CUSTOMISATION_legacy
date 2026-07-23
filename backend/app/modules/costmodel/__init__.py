# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""5D Cost Model module.

Provides 5D cost management - S-curves, cash flow projections,
earned value analysis (EVM), and budget tracking integrated with
BOQ positions and project schedules.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions and event subscribers."""
    from app.modules.costmodel.events import register_costmodel_subscribers
    from app.modules.costmodel.permissions import register_costmodel_permissions

    register_costmodel_permissions()
    register_costmodel_subscribers()
