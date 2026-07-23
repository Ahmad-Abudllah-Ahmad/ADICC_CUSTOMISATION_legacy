# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""ESG module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_esg_permissions() -> None:
    """Register permissions for the ESG Site Performance module.

    Two permissions: viewers can read the metric catalogue, readings and the
    dashboard; editors can record, update and delete readings.
    """
    permission_registry.register_module_permissions(
        "esg",
        {
            "esg.read": Role.VIEWER,
            "esg.write": Role.EDITOR,
        },
    )
