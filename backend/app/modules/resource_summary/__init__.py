# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Resource Summary module.

Turns the resource split already stored on every priced BoQ position into one
procurement-ready statement for the whole estimate: total labour-hours and cost,
and the total quantity and cost of each material, machine and subcontract line. It
answers the buyer's first question - "given this estimate, what and how much do we
actually have to procure?" - which the per-position price build-up
(:mod:`app.modules.price_breakdown`) cannot, because it never aggregates demand
across positions.

The aggregation core (:mod:`app.modules.resource_summary.aggregate`) is a pure,
``Decimal``-exact library with no ORM or database dependency, so it unit-tests from
plain dicts. Permission registration is deferred to :func:`on_startup`, called by
the module loader.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions."""
    from app.modules.resource_summary.permissions import register_resource_summary_permissions

    register_resource_summary_permissions()
