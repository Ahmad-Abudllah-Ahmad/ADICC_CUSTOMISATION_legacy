# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Service & Maintenance module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_service",
    version="0.1.0",
    display_name="Service & Maintenance",
    description=(
        "Service contracts, tickets, work orders, SLA tracking, and "
        "preventive-maintenance scheduling for MEP and facility service teams."
    ),
    author="OpenConstructionERP Core Team",
    category="business",
    depends=["oe_users", "oe_projects", "oe_contacts"],
    auto_install=True,
    enabled=True,
)
