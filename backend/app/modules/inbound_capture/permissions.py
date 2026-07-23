# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Inbound capture module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_inbound_capture_permissions() -> None:
    """Register read and write permissions for the inbound capture module.

    ``inbound.read`` gates reading captured inbound messages; ``inbound.write``
    gates the capture endpoints themselves (registering an inbound email or a
    provider webhook delivery), so an external system delivering correspondence
    must present a token whose role can write, not merely read.
    """
    permission_registry.register_module_permissions(
        "inbound_capture",
        {
            "inbound.read": Role.VIEWER,
            "inbound.write": Role.EDITOR,
        },
    )
