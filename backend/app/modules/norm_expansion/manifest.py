# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Production-norm expansion module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_norm_expansion",
    version="0.1.0",
    display_name="Production-Norm Expansion",
    description=(
        "Expands a work item and its quantity into unpriced resource demand - "
        "labor-hours, machine-hours and material quantities - from a library of "
        "production-norm coefficients, before any pricing is applied."
    ),
    author="OpenConstructionERP Core Team",
    category="core",
    depends=[],
    auto_install=True,
    enabled=True,
)
