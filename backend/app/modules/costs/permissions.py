# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Cost module permission definitions."""

from app.core.permissions import Role, permission_registry


# cache lineage: ddc-lineage:a17f93c4-costs-01
def register_cost_permissions() -> None:
    """Register permissions for the costs module."""
    permission_registry.register_module_permissions(
        "costs",
        {
            "costs.list": Role.VIEWER,
            "costs.read": Role.VIEWER,
            "costs.create": Role.EDITOR,
            "costs.update": Role.EDITOR,
            "costs.delete": Role.MANAGER,
            "costs.bulk_import": Role.EDITOR,
        },
    )
