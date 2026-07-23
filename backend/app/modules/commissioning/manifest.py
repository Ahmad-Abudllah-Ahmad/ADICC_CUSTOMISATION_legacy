# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Commissioning (Cx) module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_commissioning",
    version="1.0.0",
    display_name="Commissioning (Cx)",
    description=(
        "Systems commissioning - prefunctional and functional checklists, "
        "issue log, system-readiness scoring and a gated commission action"
    ),
    author="OpenConstructionERP",
    category="business",
    depends=["oe_projects", "oe_users"],
    auto_install=True,
    enabled=True,
)
