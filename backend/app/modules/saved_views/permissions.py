# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Saved-views module permission definitions.

RBAC gates WHETHER you may use the feature; the scoper gates WHICH rows. Both
always run: holding ``saved_views.read`` does not let a viewer read an entity
they have no project access to, because the scoper still calls
``verify_project_access``.
"""

from app.core.permissions import Role, permission_registry


def register_saved_views_permissions() -> None:
    """Register permissions for the saved-views module."""
    permission_registry.register_module_permissions(
        "saved_views",
        {
            "saved_views.read": Role.VIEWER,
            "saved_views.create": Role.EDITOR,
            "saved_views.update": Role.EDITOR,
            "saved_views.delete": Role.EDITOR,
            "saved_views.export": Role.VIEWER,
        },
    )
