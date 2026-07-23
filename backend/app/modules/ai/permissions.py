# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""AI module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_ai_permissions() -> None:
    """Register permissions for the AI module."""
    permission_registry.register_module_permissions(
        "ai",
        {
            "ai.settings.read": Role.VIEWER,
            "ai.settings.update": Role.EDITOR,
            "ai.estimate": Role.EDITOR,
            "ai.create_boq": Role.EDITOR,
            "ai.use": Role.EDITOR,
        },
    )
