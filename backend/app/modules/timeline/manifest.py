# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Timeline module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_timeline",
    version="0.1.0",
    display_name="Project Timeline",
    description=(
        "Unified, cross-module project timeline over the existing "
        "activity-log store (no new table) - a newest-first, filterable feed "
        "of significant domain events rolled up to their umbrella project, "
        "plus an event-bus bridge subscriber that persists those events so "
        "the timeline survives a restart"
    ),
    author="OpenConstructionERP Core Team",
    category="core",
    depends=["oe_users", "oe_projects"],
    auto_install=True,
    enabled=True,
)
