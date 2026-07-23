# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""BCF module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_bcf_permissions() -> None:
    """Register RBAC permissions for the BCF module.

    Mirrors the verb set used by sibling modules (``cde``, ``validation``):
    read for viewers, create/update for editors, delete for managers.
    Import is treated as a create-class mutation; export is a read.
    """
    permission_registry.register_module_permissions(
        "bcf",
        {
            "bcf.read": Role.VIEWER,
            "bcf.create": Role.EDITOR,
            "bcf.update": Role.EDITOR,
            "bcf.delete": Role.MANAGER,
            "bcf.import": Role.EDITOR,
            "bcf.export": Role.VIEWER,
        },
    )
