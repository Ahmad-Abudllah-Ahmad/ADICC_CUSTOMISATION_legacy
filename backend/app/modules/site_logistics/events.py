# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site Logistics event topics.

Events are published best-effort via ``event_bus.publish_detached`` from the
service layer so other modules (notifications, dashboards, field team) can react
to delivery activity without importing the site-logistics ORM.

    site_logistics.delivery.booked    - a new delivery was booked
    site_logistics.delivery.approved  - a delivery was approved and holds its slot
    site_logistics.delivery.rejected  - a delivery was declined
"""

from __future__ import annotations

DELIVERY_BOOKED = "site_logistics.delivery.booked"
DELIVERY_APPROVED = "site_logistics.delivery.approved"
DELIVERY_REJECTED = "site_logistics.delivery.rejected"
