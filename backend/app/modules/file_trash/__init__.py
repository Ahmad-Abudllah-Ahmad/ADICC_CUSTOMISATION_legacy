# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File Recycle Bin (soft-delete) module.

Centralised trash table that snapshots a deleted row from any of the
8 file-kind tables. Avoids adding a ``deleted_at`` column to each
kind table (which would touch every existing model). Instead each
deleted row dumps its full payload into ``oe_file_trash.payload_json``
and the original row is removed. Restore re-inserts via the
appropriate kind repository.
"""


async def on_startup() -> None:
    """Module startup hook - register RBAC permissions."""
    from app.modules.file_trash.permissions import register_file_trash_permissions

    register_file_trash_permissions()
