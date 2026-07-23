# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Closeout module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_closeout_permissions() -> None:
    """Register permissions for the closeout module.

    ``closeout.verify`` is gated at MANAGER because confirming that a piece
    of evidence is correct is a sign-off act, not routine editing.
    """
    permission_registry.register_module_permissions(
        "closeout",
        {
            "closeout.read": Role.VIEWER,
            "closeout.create": Role.EDITOR,
            "closeout.update": Role.EDITOR,
            "closeout.delete": Role.MANAGER,
            "closeout.build": Role.EDITOR,
            "closeout.verify": Role.MANAGER,
        },
    )
