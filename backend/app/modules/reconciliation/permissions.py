# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Event-reconciliation module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_reconciliation_permissions() -> None:
    """Register read and write permissions for the reconciliation module."""
    permission_registry.register_module_permissions(
        "reconciliation",
        {
            "reconciliation.read": Role.VIEWER,
            "reconciliation.write": Role.EDITOR,
        },
    )
