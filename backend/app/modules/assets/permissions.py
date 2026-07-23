# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Asset Operations permission definitions.

Reads ride ``bim.read`` (assets ARE BIM elements). Dispatching warranty
alerts is a manager-level act because it fans out notifications to the
whole project team, so it gets its own ``assets.alert`` permission.
"""

from app.core.permissions import Role, permission_registry


def register_assets_permissions() -> None:
    """Register Asset Operations permissions."""
    permission_registry.register_module_permissions(
        "assets",
        {
            "assets.read": Role.VIEWER,
            "assets.alert": Role.MANAGER,
        },
    )
