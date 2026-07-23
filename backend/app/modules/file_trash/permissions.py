# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File Trash module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_file_trash_permissions() -> None:
    """Register RBAC permissions for the file_trash module."""
    permission_registry.register_module_permissions(
        "file_trash",
        {
            "file_trash.read": Role.VIEWER,
            "file_trash.write": Role.EDITOR,
            "file_trash.restore": Role.EDITOR,
            "file_trash.purge": Role.MANAGER,
        },
    )
