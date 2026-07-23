# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Phone-log module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_phonelog",
    version="0.1.0",
    display_name="Phone Log",
    description=(
        "Capture phone calls, voice notes, and verbal instructions as dispute-ready records - "
        "parties, direction, duration, a short summary, and the instruction-bearing sentences "
        "pulled out of the transcript - so a spoken instruction is on the project record"
    ),
    author="OpenConstructionERP Core Team",
    category="core",
    depends=["oe_users", "oe_projects"],
    auto_install=True,
    enabled=True,
)
