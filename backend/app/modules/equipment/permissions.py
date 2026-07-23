# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Equipment module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_equipment_permissions() -> None:
    """Register permissions for the equipment module."""
    permission_registry.register_module_permissions(
        "equipment",
        {
            "equipment.create": Role.MANAGER,
            "equipment.read": Role.VIEWER,
            "equipment.update": Role.MANAGER,
            "equipment.delete": Role.MANAGER,
            "equipment.assign": Role.EDITOR,
            "equipment.record_telemetry": Role.EDITOR,
            "equipment.complete_maintenance": Role.EDITOR,
            "equipment.record_damage": Role.VIEWER,
            "equipment.approve_inspection": Role.MANAGER,
        },
    )
