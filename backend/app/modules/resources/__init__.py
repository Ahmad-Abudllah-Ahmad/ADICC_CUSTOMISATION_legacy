# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Resources (Graphical Resource Planning) module.

Manages resources (people, crews, equipment, subcontractors) with skills,
certifications, availability windows, assignments to projects/tasks/work orders,
conflict detection, skill-based matching, and resource requests.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions."""
    from app.modules.resources.permissions import register_resources_permissions

    register_resources_permissions()
