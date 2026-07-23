# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Carbon module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_carbon_permissions() -> None:
    """Register permissions for the Carbon & Sustainability module."""
    permission_registry.register_module_permissions(
        "carbon",
        {
            "carbon.read": Role.VIEWER,
            "carbon.create": Role.EDITOR,
            "carbon.update": Role.EDITOR,
            "carbon.delete": Role.MANAGER,
            "carbon.finalize_inventory": Role.MANAGER,
            "carbon.set_targets": Role.MANAGER,
            "carbon.generate_report": Role.EDITOR,
            "carbon.import_epd": Role.MANAGER,
        },
    )
