# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Inbound Capture Gateway module.

Captures correspondence arriving from outside the app - a forwarded email, a
chat / generic webhook, an SMS gateway - and turns it into incoming
correspondence. The pure :mod:`normalize` engine flattens each channel's ad-hoc
payload to a single canonical :class:`~app.modules.inbound_capture.normalize.InboundMessage`
(stdlib only, so it unit-tests on the local runner without the database or web
framework); a thin service persists that message as an ``oe_correspondence`` row
with ``direction = incoming`` and publishes ``correspondence.created`` so the
same downstream consumers (vector indexer, comms digest) that see hand-entered
correspondence also see captured messages.

The module loader discovers and mounts the ``router`` submodule and calls
:func:`on_startup` once at boot; this ``__init__`` does not import the router or
the service at top level so the engine stays independently importable.
"""

__all__ = ["on_startup"]


async def on_startup() -> None:
    """Module startup hook - register the module's permissions."""
    from app.modules.inbound_capture.permissions import (
        register_inbound_capture_permissions,
    )

    register_inbound_capture_permissions()
