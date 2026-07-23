# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Architecture Map module permission definitions.

The architecture manifest leaks substantial structural detail about the
deployed system - every module's file list, every ORM model + table name +
column types, inter-module dependency edges. That is gold for an attacker
mapping an unknown ERP instance ("which models exist? which routes
deserve probing?") and adds nothing for an estimator / project manager
doing day-to-day cost work.

Therefore the entire surface is gated to ``architecture.read`` at
``Role.ADMIN``. Developers and ops staff (the actual audience for the
interactive map) already hold admin or can be granted the permission
without widening any other gate.
"""

from app.core.permissions import Role, permission_registry


def register_architecture_map_permissions() -> None:
    """Register RBAC permissions for the architecture-map module."""
    permission_registry.register_module_permissions(
        "architecture_map",
        {
            "architecture.read": Role.ADMIN,
        },
    )
