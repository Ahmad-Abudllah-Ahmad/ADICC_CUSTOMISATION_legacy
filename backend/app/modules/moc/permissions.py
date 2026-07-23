# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Management of Change (MoC) module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_moc_permissions() -> None:
    """Register permissions for the MoC module."""
    permission_registry.register_module_permissions(
        "moc",
        {
            "moc.read": Role.VIEWER,
            "moc.create": Role.EDITOR,
            "moc.update": Role.EDITOR,
            "moc.delete": Role.MANAGER,
            "moc.review": Role.MANAGER,
            "moc.approve": Role.MANAGER,
            "moc.implement": Role.EDITOR,
        },
    )
