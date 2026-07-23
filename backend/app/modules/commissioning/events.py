# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Commissioning (Cx) module events.

Defines the module's outbound event names and a thin, fail-soft emit helper so
the emit call site in the service reads in one line and other modules
(notifications, analytics, closeout) can subscribe without importing the
service. There are no inbound subscribers yet, so importing this module at load
time has no side effects.
"""

from __future__ import annotations

import logging

from app.core.events import event_bus

logger = logging.getLogger(__name__)

#: Emitted once, after a system successfully passes the commission gate and is
#: marked ``commissioned``.
SYSTEM_COMMISSIONED = "commissioning.system.commissioned"


def emit_system_commissioned(
    *,
    project_id: str,
    system_id: str,
    system_name: str,
    system_type: str,
    readiness_pct: float,
    user_id: str | None = None,
) -> None:
    """Publish :data:`SYSTEM_COMMISSIONED` for cross-module handlers.

    Uses ``event_bus.publish_detached`` so a slow or failing subscriber can
    never roll back or block the commissioning transaction that triggered it.
    """
    try:
        event_bus.publish_detached(
            SYSTEM_COMMISSIONED,
            data={
                "project_id": project_id,
                "system_id": system_id,
                "system_name": system_name,
                "system_type": system_type,
                "readiness_pct": readiness_pct,
                "user_id": user_id,
            },
            source_module="commissioning",
        )
    except Exception:
        logger.debug("commissioning: system_commissioned emit failed", exc_info=True)
