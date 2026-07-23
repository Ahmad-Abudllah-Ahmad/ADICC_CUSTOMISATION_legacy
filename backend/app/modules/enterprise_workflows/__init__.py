# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Enterprise Workflows module.

Configurable approval workflows for invoices, purchase orders,
variations, and BOQs.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions."""
    from app.modules.enterprise_workflows.permissions import (
        register_enterprise_workflows_permissions,
    )

    register_enterprise_workflows_permissions()
