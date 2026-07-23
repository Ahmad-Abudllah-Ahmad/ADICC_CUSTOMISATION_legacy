# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Carbon & Sustainability module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_carbon",
    version="0.1.0",
    display_name="Carbon & Sustainability",
    description=(
        "Embodied + operational carbon (scope 1/2/3), EPD database, "
        "material matching, targets, sustainability reporting "
        "(GHG Protocol / GRI / ISSB)"
    ),
    author="OpenConstructionERP Core Team",
    category="business",
    depends=["oe_users", "oe_projects"],
    auto_install=True,
    enabled=True,
)
