# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Service & Maintenance permission definitions."""

from app.core.permissions import Role, permission_registry

# Public list of permissions registered by this module. Exposed as a constant
# so tests and admin tooling can introspect the contract without import-time
# side effects.
SERVICE_PERMISSIONS: dict[str, Role] = {
    "service.create": Role.EDITOR,
    "service.read": Role.VIEWER,
    "service.update": Role.EDITOR,
    "service.delete": Role.MANAGER,
    "service.dispatch": Role.MANAGER,
    "service.bill": Role.MANAGER,
    "service.close_contract": Role.MANAGER,
}


def register_service_permissions() -> None:
    """Register permissions for the Service & Maintenance module."""
    permission_registry.register_module_permissions("service", SERVICE_PERMISSIONS)
