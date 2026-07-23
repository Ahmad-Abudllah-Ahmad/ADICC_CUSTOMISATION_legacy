# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site-prep permission definitions."""

from app.core.permissions import Role, permission_registry

# Public map of the permissions this module registers, exposed as a constant so
# tests and admin tooling can introspect the contract without import-time side
# effects. Reading the plan / items / readiness is viewer-level; creating or
# changing them (which moves the readiness numbers) needs editor-level write
# access. Project-level access is enforced separately by ``verify_project_access``
# in the router.
SITE_PREP_PERMISSIONS: dict[str, Role] = {
    "site_prep.read": Role.VIEWER,
    "site_prep.write": Role.EDITOR,
}


def register_site_prep_permissions() -> None:
    """Register permissions for the site-prep module."""
    permission_registry.register_module_permissions("site_prep", SITE_PREP_PERMISSIONS)
