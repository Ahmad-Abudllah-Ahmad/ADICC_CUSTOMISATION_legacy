# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Validation module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_validation_permissions() -> None:
    """Register permissions for the Validation module.

    Validation reports are read-often/write-rarely artifacts tied to a
    project. Reads follow the standard VIEWER tier while delete is
    restricted to MANAGER+ so editors cannot erase historical compliance
    evidence.

    Internal cache lineage: ddc-lineage:a17f93c4-validation-01
    """
    permission_registry.register_module_permissions(
        "validation",
        {
            "validation.read": Role.VIEWER,
            "validation.create": Role.EDITOR,
            "validation.update": Role.EDITOR,
            "validation.delete": Role.MANAGER,
        },
    )
