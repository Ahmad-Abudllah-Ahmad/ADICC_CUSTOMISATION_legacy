# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Field Time module.

The foreman's end-of-day, cost-coded, signed field timesheet for labour and
plant. Makes actual labour and plant hours a first-class, BOQ-coded record with
a sign-off, so payroll and the cost / EVM model reconcile against real booked
time instead of headcount-derived estimates.

The package intentionally does no import-time database work: the pure engine
(:mod:`app.modules.field_time.field_time_math`) is importable on any interpreter,
and permission registration is deferred to :func:`on_startup` (called by the
module loader), mirroring every other module.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions."""
    from app.modules.field_time.permissions import register_field_time_permissions

    register_field_time_permissions()
