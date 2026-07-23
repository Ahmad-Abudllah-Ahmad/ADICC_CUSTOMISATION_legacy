# OpenConstructionERP - DataDrivenConstruction (DDC)
# DDC-CWICR-OE-2026
"""Progress module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_progress_permissions() -> None:
    """Register permissions for the progress module."""
    permission_registry.register_module_permissions(
        "progress",
        {
            "progress.create": Role.EDITOR,
            "progress.read": Role.VIEWER,
            "progress.update": Role.EDITOR,
            "progress.delete": Role.MANAGER,
            "progress.plan_edit": Role.MANAGER,
        },
    )
