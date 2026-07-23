# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File Versioning module.

Tracks polymorphic version chains for the 8 file kinds the file
manager surfaces (document / photo / sheet / bim_model / dwg_drawing
/ takeoff / report / markup). A re-upload of the same canonical
name within a project rolls forward the chain: the old row is
flagged ``superseded`` and a new row becomes ``is_current=True``.
"""


async def on_startup() -> None:
    """Module startup hook - register RBAC permissions."""
    from app.modules.file_versions.permissions import register_file_version_permissions

    register_file_version_permissions()
