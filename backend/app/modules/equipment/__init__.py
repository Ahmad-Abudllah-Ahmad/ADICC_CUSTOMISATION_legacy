# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Equipment & Fleet Management module.

Owned/rented/leased equipment fleet with telemetry, maintenance scheduling,
inspections, internal rental billing, fuel tracking, parts management,
and damage reports.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions and event subscribers."""
    from app.modules.equipment.events import register_equipment_subscribers
    from app.modules.equipment.permissions import register_equipment_permissions

    register_equipment_permissions()
    register_equipment_subscribers()
