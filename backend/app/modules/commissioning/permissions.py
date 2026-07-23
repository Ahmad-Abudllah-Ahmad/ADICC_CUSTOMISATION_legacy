# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Commissioning (Cx) module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_commissioning_permissions() -> None:
    """Register permissions for the Commissioning module.

    Reading systems, checklists and issues is open to any viewer. Every
    mutation - creating, editing and deleting systems, checklists, items and
    issues - is a single editor-level ``write`` action. The final gated
    ``commission`` action, which certifies a system as ready for handover, is a
    manager-level responsibility.
    """
    permission_registry.register_module_permissions(
        "commissioning",
        {
            "commissioning.read": Role.VIEWER,
            "commissioning.write": Role.EDITOR,
            "commissioning.commission": Role.MANAGER,
        },
    )
