# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Preliminaries (general conditions) module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_preliminaries",
    version="1.0.0",
    display_name="Preliminaries",
    description=(
        "General conditions / preliminaries estimator. Prices site establishment, "
        "site staff, temporary works, standing plant and welfare as time-related "
        "items (a rate per period times the project duration) plus fixed one-off "
        "items, and rolls them up per category into a preliminaries total that adds "
        "to the estimate alongside the measured work."
    ),
    author="OpenConstructionERP Core Team",
    category="core",
    depends=["oe_projects"],
    auto_install=True,
    enabled=True,
)
