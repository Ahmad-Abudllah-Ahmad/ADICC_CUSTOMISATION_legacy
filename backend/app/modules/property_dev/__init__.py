# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Property Development & Buyer Portal module.

Tracks property developments, plots, house types, buyer option catalogues,
buyer registrations + selections (with freeze deadlines), handovers + snag
lists and post-handover warranty claims. Provides the data foundation and
business logic for a downstream 3D configurator + portal frontend.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions + event subscribers."""
    from app.modules.property_dev.events import (
        register_portal_message_subscribers,
        register_property_dev_event_subscribers,
        register_subscribers,
        register_task_139_subscribers,
        register_warranty_bridge_subscribers,
    )
    from app.modules.property_dev.permissions import register_property_dev_permissions

    register_property_dev_permissions()
    register_property_dev_event_subscribers()
    register_subscribers()
    register_task_139_subscribers()
    register_warranty_bridge_subscribers()
    register_portal_message_subscribers()
