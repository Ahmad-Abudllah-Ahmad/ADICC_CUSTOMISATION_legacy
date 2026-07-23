"""Event bus primitives, re-exported from the platform core.

The event bus lets modules react to each other without importing each other.
There is one process-global instance, ``event_bus``. Subscribe with the ``on``
decorator, publish with ``publish`` (awaited, returns an ``EventResult`` with
per-handler outcomes) or ``publish_detached`` (fire and forget). Event names are
dot-notation, ``{module}.{entity}.{action}``. See ``app.core.events`` for the
implementation and semantics (sync handlers run in a thread, one failing handler
never stops the others, ``*`` is a wildcard subscription).
"""

from __future__ import annotations

from app.core.events import Event, EventBus, EventResult, event_bus

# Bound-method conveniences so a module can write `from oe_sdk import on` and
# `@on("module.entity.action")`, exactly like the docs show with
# `@event_bus.on(...)`. Each is bound to the global singleton, so it registers
# on and dispatches through the same bus the platform uses.
on = event_bus.on
publish = event_bus.publish
publish_detached = event_bus.publish_detached
subscribe = event_bus.subscribe

__all__ = [
    "event_bus",
    "Event",
    "EventResult",
    "EventBus",
    "on",
    "publish",
    "publish_detached",
    "subscribe",
]
