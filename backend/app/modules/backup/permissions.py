# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Backup module permission definitions.

The router declares ``RequirePermission("backup.admin")`` on export,
import and purge endpoints, but the module never registered the
permission with the live registry, so every non-admin role received a
403 with a stray "Unknown permission checked" WARN. Admins succeeded
only via the role bypass. This file ships the missing registration.
"""

from app.core.permissions import Role, permission_registry


def register_backup_permissions() -> None:
    """Register RBAC permissions for the backup module.

    Permission layout:
        backup.admin - export / import / purge user-data backups (ADMIN only)
    """
    permission_registry.register_module_permissions(
        "backup",
        {
            "backup.admin": Role.ADMIN,
        },
    )
