# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Temporary-works permission definitions."""

from app.core.permissions import Role, permission_registry

# Public map of the permissions this module registers, exposed as a constant so
# tests and admin tooling can introspect the contract without import-time side
# effects. Reading the register / items / permits / clearance is viewer-level;
# creating or changing them (which moves the safety gates) needs editor-level
# write access. Project-level access is enforced separately by
# ``verify_project_access`` in the router.
TEMPORARY_WORKS_PERMISSIONS: dict[str, Role] = {
    "temporary_works.read": Role.VIEWER,
    "temporary_works.write": Role.EDITOR,
}


def register_temporary_works_permissions() -> None:
    """Register permissions for the temporary-works module."""
    permission_registry.register_module_permissions(
        "temporary_works",
        TEMPORARY_WORKS_PERMISSIONS,
    )
