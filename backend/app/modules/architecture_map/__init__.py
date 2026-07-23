# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Architecture Map module - admin-only system architecture viewer."""


async def on_startup() -> None:
    """Module startup hook - register permissions."""
    from app.modules.architecture_map.permissions import (
        register_architecture_map_permissions,
    )

    register_architecture_map_permissions()
