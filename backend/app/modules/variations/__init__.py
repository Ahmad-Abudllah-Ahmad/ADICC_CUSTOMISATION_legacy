# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Variations & Site Measurements module.

Covers the full variations lifecycle:

* Notice of intent -> Variation Request -> Variation Order
* Site Measurements (joint owner/contractor measurement records)
* Daywork Sheets (signed time-and-material work)
* Disruption Claims (productivity loss claims)
* Extension of Time Claims (schedule recovery requests)
* Final Account (rolled-up settlement of all variations + claims)

This is a sister module to ``oe_changeorders`` -- variations *can* be
materialised as a change order via the soft ``reference_change_order_id``
link (plain UUID, no DB-level FK to keep the two modules independent).
"""


async def on_startup() -> None:
    """Module startup hook -- register permissions."""
    from app.modules.variations.permissions import register_variations_permissions

    register_variations_permissions()
