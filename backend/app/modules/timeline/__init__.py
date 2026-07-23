# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Project Timeline module.

A unified, cross-module project timeline built on the existing activity-log
store (``oe_activity_log``) - no new table and no migration. Two pieces:

* a *read* service + API that rolls every module's activity up to its umbrella
  project (newest-first, filterable), and
* a *bridge* wildcard subscriber that persists significant domain events from
  the in-memory event bus so the timeline survives a restart.

The module loader auto-mounts ``router`` at ``/api/v1/timeline`` and calls
:func:`on_startup` once at boot.
"""

from app.modules.timeline.router import router

__all__ = ["router", "on_startup"]


async def on_startup() -> None:
    """Module startup hook - register the event-bus bridge subscriber.

    The module loader auto-calls this when the module package is discovered.
    """
    from app.modules.timeline.events import register_timeline_subscribers

    register_timeline_subscribers()
