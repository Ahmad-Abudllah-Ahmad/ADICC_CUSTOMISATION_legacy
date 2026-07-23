# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Estimate-rollup module.

Composes a project's full estimate total - the BOQ base (measured works plus
markups), the preliminaries register and the remaining allowances / contingency -
into one headline number with a line-item breakdown, so the figures that live in
separate estimating tools finally roll up into the number a client sees.

The composition logic lives in the dependency-free
:mod:`app.modules.estimate_rollup.composition` engine that unit-tests on the
local runner; the service and router are a thin, read-only database / HTTP layer
on top that reuses each sibling module's own authoritative rollup. The module
loader discovers and mounts the ``router`` submodule at ``/api/v1/estimate-rollup``
and calls :func:`on_startup` once at boot. This package ``__init__`` deliberately
does not import the router at top level so the pure engine stays importable
without the database / framework stack. The module owns no ORM models, so no
Alembic migration is authored for it.
"""

__all__ = ["on_startup"]


async def on_startup() -> None:
    """Module startup hook - register the module's permissions."""
    from app.modules.estimate_rollup.permissions import register_estimate_rollup_permissions

    register_estimate_rollup_permissions()
