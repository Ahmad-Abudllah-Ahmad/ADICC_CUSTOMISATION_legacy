# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Payroll module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_payroll",
    version="0.1.0",
    display_name="Payroll",
    description=(
        "Draft payroll batches from field labour - aggregates site workforce "
        "and field-diary hours per worker/date into entries (hours x rate)."
    ),
    author="OpenConstructionERP Core Team",
    category="core",
    depends=["oe_projects", "oe_fieldreports", "oe_resources"],
    auto_install=True,
    enabled=True,
)
