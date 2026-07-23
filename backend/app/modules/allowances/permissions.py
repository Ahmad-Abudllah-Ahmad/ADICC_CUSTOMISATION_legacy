# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Allowances register permission definitions."""

from app.core.permissions import Role, permission_registry


def register_allowances_permissions() -> None:
    """Register the read / write permissions for the allowances module.

    Reading the register is open to viewers; creating allowances and recording
    drawdowns is an editor-level action, matching the other estimate-side
    commercial modules.
    """
    permission_registry.register_module_permissions(
        "allowances",
        {
            "allowances.read": Role.VIEWER,
            "allowances.write": Role.EDITOR,
        },
    )
