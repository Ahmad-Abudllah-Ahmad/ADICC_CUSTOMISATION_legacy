# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Bid Management module.

Sister module to ``oe_tendering``. Provides a richer bid package /
invitation / submission / leveling / award workflow without modifying
the existing ``tendering`` module. ``tender_id`` is a plain UUID
reference (no FK across modules).
"""


async def on_startup() -> None:
    """Module startup hook - register permissions."""
    from app.modules.bid_management.permissions import register_bid_management_permissions

    register_bid_management_permissions()
