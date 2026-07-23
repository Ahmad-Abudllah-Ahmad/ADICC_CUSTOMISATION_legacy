# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Conceptual (ROM) estimate module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_rom_estimate_permissions() -> None:
    """Register permissions for the conceptual estimate module."""
    permission_registry.register_module_permissions(
        "rom_estimate",
        {
            "rom_estimate.read": Role.VIEWER,
            "rom_estimate.write": Role.EDITOR,
        },
    )
