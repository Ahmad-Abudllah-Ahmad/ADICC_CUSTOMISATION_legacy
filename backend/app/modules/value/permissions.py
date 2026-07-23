# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Value Realized permission definitions."""

from app.core.permissions import Role, permission_registry


def register_value_permissions() -> None:
    """Register the analytical read permission for the value-realized module."""
    permission_registry.register_module_permissions(
        "value",
        {
            "value.read": Role.VIEWER,
        },
    )
