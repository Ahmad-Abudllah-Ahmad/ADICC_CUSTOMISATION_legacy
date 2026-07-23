# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site-inventory permission definitions."""

from app.core.permissions import Role, permission_registry

# Public map of the permissions this module registers, exposed as a constant so
# tests and admin tooling can introspect the contract without import-time
# side effects. Reading stock is viewer-level; recording a movement (which
# changes the stock ledger) needs editor-level write access. Project-level
# access is enforced separately by ``verify_project_access`` in the router.
SITE_INVENTORY_PERMISSIONS: dict[str, Role] = {
    "site_inventory.read": Role.VIEWER,
    "site_inventory.write": Role.EDITOR,
}


def register_site_inventory_permissions() -> None:
    """Register permissions for the site-inventory module."""
    permission_registry.register_module_permissions("site_inventory", SITE_INVENTORY_PERMISSIONS)
