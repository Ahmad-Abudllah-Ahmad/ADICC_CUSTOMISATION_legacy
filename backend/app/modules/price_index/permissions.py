# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Price-index module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_price_index_permissions() -> None:
    """Register permissions for the Price Index module.

    Reads are open to any viewer; managing the shared index series and
    regional factors (which re-price every estimate that adjusts against
    them) is gated at editor level.
    """
    permission_registry.register_module_permissions(
        "price_index",
        {
            "price_index.read": Role.VIEWER,
            "price_index.manage": Role.EDITOR,
        },
    )
