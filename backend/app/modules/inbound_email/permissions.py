# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Inbound email module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_inbound_email_permissions() -> None:
    """Register the read permission for the inbound email module."""
    permission_registry.register_module_permissions(
        "inbound_email",
        {
            "inbound_email.read": Role.VIEWER,
        },
    )
