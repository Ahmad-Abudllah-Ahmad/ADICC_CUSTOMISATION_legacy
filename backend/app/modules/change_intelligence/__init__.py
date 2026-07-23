# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Change Intelligence module.

A thin analytical layer over the change-management family (change orders,
variation notices / requests / orders, management-of-change entries). It does
not own any change records; it reads them and answers the team's recurring
questions about open changes: what is waiting on whom and for how long
(cycle-time telemetry), what an approved change does to cost and schedule
(impact projection), and how to turn a rough change note into a well-formed
request (clarifier).

The decision logic lives in dependency-free engines (``cycle_time``,
``impact_projection``, ``clarifier``) that unit-test on the local runner; the
service and router are a thin database / HTTP layer on top.

The module loader discovers and mounts the ``router`` submodule at
``/api/v1/change-intelligence`` and calls :func:`on_startup` once at boot. This
package ``__init__`` deliberately does not import the router at top level so
the pure engines remain importable without the database / framework stack.
"""

__all__ = ["on_startup"]


async def on_startup() -> None:
    """Module startup hook - register the module's permissions."""
    from app.modules.change_intelligence.permissions import (
        register_change_intelligence_permissions,
    )

    register_change_intelligence_permissions()
