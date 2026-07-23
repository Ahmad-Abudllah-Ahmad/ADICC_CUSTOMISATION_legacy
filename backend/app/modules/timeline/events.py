# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Timeline bridge subscriber - persist significant events to the audit store.

The in-memory event bus (:mod:`app.core.events`) loses everything on restart.
This bridge subscribes a single wildcard handler that, for each *significant*
cross-module domain event (see :mod:`app.modules.timeline.mapping`), writes one
:class:`app.core.audit_log.ActivityLog` row so the unified project timeline
survives a process restart.

The handler is best-effort: it opens its own async session (publishers may
already hold one; on embedded PostgreSQL a concurrent second session for a
short write is fine), and the whole body is wrapped so a failure here can
*never* break the publisher. Registration is idempotent.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.audit_log import log_activity
from app.core.events import event_bus
from app.database import async_session_factory
from app.modules.timeline import mapping

if TYPE_CHECKING:
    from app.core.events import Event

logger = logging.getLogger(__name__)

_SUBSCRIBED_FLAG = "_timeline_subscribers_registered"


async def _record_event(event: Event) -> None:
    """Persist a significant event as one ActivityLog row (best-effort).

    Wrapped end-to-end in try/except: a malformed event, a mapping miss, or a
    DB hiccup is logged at WARNING and swallowed so the publishing workflow is
    never affected.
    """
    try:
        if not mapping.is_significant(event.name):
            return
        mapped = mapping.map_event(event.name, event.data or {})
        if mapped is None:
            return

        metadata = {
            **mapped.get("metadata", {}),
            "_via": "event_bus",
            "event_id": event.id,
        }

        async with async_session_factory() as session:
            await log_activity(
                session,
                actor_id=None,
                action=mapped["action"],
                entity_type=mapped["entity_type"],
                entity_id=mapped["entity_id"],
                module=mapped["module"],
                parent_entity_type=mapped["parent_entity_type"],
                parent_entity_id=mapped["parent_entity_id"],
                metadata=metadata,
            )
            await session.commit()
        logger.debug("timeline: recorded event %s (%s)", event.name, event.id)
    except Exception:  # noqa: BLE001 - best-effort, never break the publisher
        logger.warning(
            "timeline: failed to record event %s",
            getattr(event, "name", "<unknown>"),
            exc_info=True,
        )


def register_timeline_subscribers() -> None:
    """Subscribe the wildcard bridge handler to the event bus (idempotent)."""
    if getattr(event_bus, _SUBSCRIBED_FLAG, False):
        return
    event_bus.subscribe("*", _record_event)
    try:
        setattr(event_bus, _SUBSCRIBED_FLAG, True)
    except (AttributeError, TypeError):
        pass
    logger.info("timeline: wildcard bridge subscriber registered")
