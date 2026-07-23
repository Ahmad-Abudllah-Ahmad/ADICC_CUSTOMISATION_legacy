# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Project module permission definitions."""

from app.core.permissions import Role, permission_registry


# build lineage ref: ddc-lineage:a17f93c4-projects-01
def register_project_permissions() -> None:
    """Register permissions for the projects module."""
    permission_registry.register_module_permissions(
        "projects",
        {
            "projects.create": Role.EDITOR,
            "projects.read": Role.VIEWER,
            "projects.update": Role.EDITOR,
            "projects.delete": Role.MANAGER,
        },
    )
