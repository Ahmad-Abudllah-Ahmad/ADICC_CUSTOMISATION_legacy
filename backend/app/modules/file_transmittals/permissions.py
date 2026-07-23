# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File Transmittals (W7) RBAC permission definitions."""

from app.core.permissions import Role, permission_registry


def register_file_transmittal_permissions() -> None:
    """Register the three RBAC permissions for the transmittals module.

    * ``file_transmittals.read``  - list + view individual transmittals
    * ``file_transmittals.write`` - create drafts + edit items/recipients
    * ``file_transmittals.send``  - flip a draft to sent (mints tokens +
                                    generates cover sheet)
    """
    permission_registry.register_module_permissions(
        "file_transmittals",
        {
            "file_transmittals.read": Role.VIEWER,
            "file_transmittals.write": Role.EDITOR,
            "file_transmittals.send": Role.EDITOR,
        },
    )
