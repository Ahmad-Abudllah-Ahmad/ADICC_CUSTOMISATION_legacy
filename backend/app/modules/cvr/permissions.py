# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""CVR module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_cvr_permissions() -> None:
    """Register permissions for the CVR module."""
    permission_registry.register_module_permissions(
        "cvr",
        {
            "cvr.read": Role.VIEWER,
            "cvr.write": Role.EDITOR,
            # Striking a report "final" is a commercial sign-off, so it sits at
            # MANAGER, one rung above the day-to-day editing (cvr.write) that
            # fills the report in.
            "cvr.finalize": Role.MANAGER,
        },
    )
