# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File Versioning module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_file_version_permissions() -> None:
    """Register RBAC permissions for the file_versions module."""
    permission_registry.register_module_permissions(
        "file_versions",
        {
            "file_versions.read": Role.VIEWER,
            "file_versions.write": Role.EDITOR,
            "file_versions.restore": Role.EDITOR,
        },
    )
