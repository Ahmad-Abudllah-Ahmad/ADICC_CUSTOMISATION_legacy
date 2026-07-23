# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Subcontractor Management module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_subcontractors",
    version="0.1.0",
    display_name="Subcontractor Management",
    description=(
        "Subcontractor lifecycle: prequalification, certificates, agreements, payment applications, retention, rating"
    ),
    author="OpenConstructionERP Core Team",
    category="business",
    depends=["oe_users", "oe_projects", "oe_contacts"],
    auto_install=True,
    enabled=True,
)
