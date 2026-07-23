# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""RFQ Bidding module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_rfq_bidding",
    version="0.1.0",
    display_name="RFQ & Bidding",
    description="Request for Quotation management with bid submission, evaluation, and award workflows",
    author="OpenConstructionERP Core Team",
    category="enterprise",
    depends=["oe_users", "oe_projects", "oe_contacts", "oe_procurement"],
    auto_install=False,
    enabled=True,
)
