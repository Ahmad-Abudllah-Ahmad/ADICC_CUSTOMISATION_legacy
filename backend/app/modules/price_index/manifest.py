# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Price Index module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_price_index",
    version="0.1.0",
    display_name="Price Index Adjustment",
    description=(
        "Bring costs from a base period and base region to a target period and "
        "region using stored construction cost index series and regional "
        "factors, without rewriting the source estimate."
    ),
    author="OpenConstructionERP Core Team",
    category="core",
    depends=["oe_costs"],
    auto_install=True,
    enabled=True,
)
