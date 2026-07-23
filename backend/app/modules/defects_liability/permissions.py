# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Defects-liability permission definitions."""

from app.core.permissions import Role, permission_registry

# Public map of the permissions this module registers, exposed as a constant so
# tests and admin tooling can introspect the contract without import-time side
# effects. Reading the register / warranties / defects / readiness is
# viewer-level; creating or changing them (which moves the register and the
# retention-release signal) needs editor-level write access. Project-level access
# is enforced separately by ``verify_project_access`` in the router.
DEFECTS_LIABILITY_PERMISSIONS: dict[str, Role] = {
    "defects_liability.read": Role.VIEWER,
    "defects_liability.write": Role.EDITOR,
}


def register_defects_liability_permissions() -> None:
    """Register permissions for the defects-liability module."""
    permission_registry.register_module_permissions(
        "defects_liability",
        DEFECTS_LIABILITY_PERMISSIONS,
    )
