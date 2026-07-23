# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Post-calculation (Nachkalkulation) module.

Reconciles a project's estimate against its site actuals - approved field
timesheets (labour and plant hours) and progress readings (installed quantity) -
into planned-vs-actual labour productivity per BoQ line and per resource category,
a project rollup, and a ranked list of productivity factors to feed back into
estimating. A stateless read/analyse layer: it adds no table and writes nothing
back, so there is no migration.
"""


async def on_startup() -> None:
    """Module startup hook - register the read permission."""
    from app.modules.postcalc.permissions import register_postcalc_permissions

    register_postcalc_permissions()
