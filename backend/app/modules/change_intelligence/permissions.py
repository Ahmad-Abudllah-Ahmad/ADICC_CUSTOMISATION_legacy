# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Change Intelligence permission definitions."""

from app.core.permissions import Role, permission_registry


def register_change_intelligence_permissions() -> None:
    """Register the analytical read permissions for the change-intelligence module."""
    permission_registry.register_module_permissions(
        "change_intelligence",
        {
            "change_intelligence.read": Role.VIEWER,
        },
    )
