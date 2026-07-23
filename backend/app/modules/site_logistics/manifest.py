# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site Logistics & Delivery module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_site_logistics",
    version="1.0.0",
    display_name="Site Logistics & Delivery",
    description=(
        "Plan and control what arrives on site: access gates with operating "
        "hours and slot capacity, material laydown zones, and a delivery "
        "booking board with approve/reject scheduling. Windows are validated "
        "against gate hours and checked for clashes so two approved deliveries "
        "never fight for the same gate."
    ),
    author="OpenConstructionERP",
    category="business",
    depends=["oe_projects", "oe_users"],
    auto_install=True,
    enabled=True,
)
