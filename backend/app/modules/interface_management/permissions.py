# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Interface-register permission definitions."""

from app.core.permissions import Role, permission_registry

# Public map of the permissions this module registers, exposed as a constant so
# tests and admin tooling can introspect the contract without import-time side
# effects. Reading the register / interfaces / actions / health is viewer-level;
# creating or changing them (which moves the register numbers) needs editor-level
# write access. Project-level access is enforced separately by
# ``verify_project_access`` in the router.
INTERFACE_MANAGEMENT_PERMISSIONS: dict[str, Role] = {
    "interface_management.read": Role.VIEWER,
    "interface_management.write": Role.EDITOR,
}


def register_interface_management_permissions() -> None:
    """Register permissions for the interface-management module."""
    permission_registry.register_module_permissions(
        "interface_management",
        INTERFACE_MANAGEMENT_PERMISSIONS,
    )
