# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Backup module - export and import user data backups."""


async def on_startup() -> None:
    """Module startup hook - register RBAC permissions."""
    from app.modules.backup.permissions import register_backup_permissions

    register_backup_permissions()
