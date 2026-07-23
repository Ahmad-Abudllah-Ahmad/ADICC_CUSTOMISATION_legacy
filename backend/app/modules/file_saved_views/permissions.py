# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File Saved Views RBAC permission definitions."""

from app.core.permissions import Role, permission_registry


def register_file_saved_view_permissions() -> None:
    """Register permissions for the file-saved-views module.

    Viewers may read their views (and any project-shared ones); editors
    may create, rename, repin, reorder and delete. No separate share
    permission - toggling ``is_shared`` is part of the write verb because
    the share is scoped to the owner's own project membership.
    """
    permission_registry.register_module_permissions(
        "file_saved_views",
        {
            "file_saved_views.read": Role.VIEWER,
            "file_saved_views.write": Role.EDITOR,
        },
    )
