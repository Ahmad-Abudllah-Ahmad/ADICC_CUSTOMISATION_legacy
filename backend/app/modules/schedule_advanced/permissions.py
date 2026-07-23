# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Schedule Advanced module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_schedule_advanced_permissions() -> None:
    """Register permissions for the schedule_advanced (Last Planner) module."""
    permission_registry.register_module_permissions(
        "schedule_advanced",
        {
            "schedule_advanced.read": Role.VIEWER,
            "schedule_advanced.create": Role.EDITOR,
            "schedule_advanced.update": Role.EDITOR,
            "schedule_advanced.delete": Role.MANAGER,
            "schedule_advanced.pull_phase": Role.EDITOR,
            "schedule_advanced.commit": Role.EDITOR,
            "schedule_advanced.clear_constraint": Role.EDITOR,
            "schedule_advanced.close_weekly": Role.MANAGER,
            "schedule_advanced.capture_baseline": Role.MANAGER,
        },
    )
