# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File Favourites module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_file_favorites_permissions() -> None:
    """Register RBAC permissions for the file_favorites module.

    Favourites + pins are personal per-user bookmarks, so the policy is
    simple: any user that can VIEW a file can also star/pin it for
    themselves. Admin can read the global aggregate for analytics.
    """
    permission_registry.register_module_permissions(
        "file_favorites",
        {
            "file_favorites.read": Role.VIEWER,
            "file_favorites.toggle": Role.VIEWER,
            "file_favorites.pin": Role.VIEWER,
            "file_favorites.aggregate_read": Role.ADMIN,
        },
    )
