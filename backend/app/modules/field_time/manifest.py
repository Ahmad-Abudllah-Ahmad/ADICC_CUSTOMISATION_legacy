# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Field Time module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_field_time",
    version="1.0.0",
    display_name="Field Time",
    description=(
        "Cost-coded, signed field timesheets for labour and plant. The foreman's "
        "end-of-day record of who and which machine worked, how long, and against "
        "which BOQ cost code - the authoritative source of actual labour and plant "
        "hours for payroll and the cost / EVM model."
    ),
    author="OpenConstructionERP Core Team",
    category="business",
    # Real foreign keys into projects (owner), resources (labour), equipment
    # (plant) and variations (daywork order). Declaring them as hard
    # dependencies keeps the load order correct and stops any of those tables
    # from being disabled while a timesheet still references them.
    depends=["oe_projects", "oe_resources", "oe_equipment", "oe_variations"],
    auto_install=True,
    enabled=True,
)
