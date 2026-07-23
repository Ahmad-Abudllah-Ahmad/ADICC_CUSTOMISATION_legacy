# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Requirements module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_requirements_permissions() -> None:
    """Register permissions for the requirements module."""
    permission_registry.register_module_permissions(
        "requirements",
        {
            "requirements.create": Role.EDITOR,
            "requirements.read": Role.VIEWER,
            "requirements.update": Role.EDITOR,
            "requirements.delete": Role.MANAGER,
        },
    )
