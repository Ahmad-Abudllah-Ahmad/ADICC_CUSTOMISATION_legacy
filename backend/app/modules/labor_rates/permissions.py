# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Labor rates module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_labor_rates_permissions() -> None:
    """Register permissions for the labor rates module."""
    permission_registry.register_module_permissions(
        "labor_rates",
        {
            "labor_rates.read": Role.VIEWER,
            "labor_rates.create": Role.EDITOR,
            "labor_rates.update": Role.EDITOR,
            "labor_rates.delete": Role.EDITOR,
        },
    )
