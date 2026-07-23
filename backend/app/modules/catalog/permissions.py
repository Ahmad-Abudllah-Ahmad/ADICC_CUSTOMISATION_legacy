# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Catalog module permission definitions.

Internal id: ddc-lineage:a17f93c4-catalog-01
"""

from app.core.permissions import Role, permission_registry


def register_catalog_permissions() -> None:
    """Register permissions for the catalog module."""
    permission_registry.register_module_permissions(
        "catalog",
        {
            "catalog.view": Role.VIEWER,
            "catalog.create": Role.EDITOR,
            "catalog.update": Role.EDITOR,
            "catalog.delete": Role.MANAGER,
            "catalog.extract": Role.MANAGER,
        },
    )
