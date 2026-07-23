# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Cost recovery module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_cost_recovery_permissions() -> None:
    """Register read and write permissions for the cost recovery module."""
    permission_registry.register_module_permissions(
        "cost_recovery",
        {
            "cost_recovery.read": Role.VIEWER,
            "cost_recovery.write": Role.EDITOR,
        },
    )
