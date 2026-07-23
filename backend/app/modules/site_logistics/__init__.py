# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site Logistics & Delivery module.

Plan and control what arrives on site:
    - Access gates with daily operating hours and per-slot capacity
    - Material laydown / storage zones
    - Delivery booking board with approve/reject scheduling

Delivery windows are validated against gate hours, and two approved deliveries
on one gate can never overlap.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions and validation rules."""
    from app.modules.site_logistics.permissions import (
        register_site_logistics_permissions,
    )
    from app.modules.site_logistics.validators import (
        register_site_logistics_validation_rules,
    )

    register_site_logistics_permissions()
    register_site_logistics_validation_rules()
