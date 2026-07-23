# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""In-process WebSocket hub for real-time notification push (Epic B / B6).

Each authenticated client subscribes to ``/api/v1/notifications/ws/``;
when ``notifications.notification.created`` fires for their user-id,
the dispatcher calls ``notifications_ws_hub.push_to_user(...)`` and
this hub fans the message out to every open socket for that user.

Design choices mirror :mod:`app.modules.collaboration_locks.presence_hub`:

* **Pure asyncio / stdlib.**  No Redis fan-out - multi-worker
  deployments only push to the worker that holds the socket.  The v2
  plan upgrades this to Postgres LISTEN/NOTIFY without touching
  callers.
* **Per-user lock + dead-socket scrub.**  ``send_json`` raises on a
  closed tab; we catch and quietly drop the socket so a leaked socket
  cannot pin memory.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class NotificationsWsHub:
    """Subscribe / broadcast / disconnect for the notifications channel."""

    def __init__(self) -> None:
        self._by_user: dict[uuid.UUID, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def join(self, user_id: uuid.UUID, ws: WebSocket) -> int:
        async with self._lock:
            sockets = self._by_user.setdefault(user_id, set())
            sockets.add(ws)
            return len(sockets)

    async def leave(self, user_id: uuid.UUID, ws: WebSocket) -> int:
        async with self._lock:
            sockets = self._by_user.get(user_id)
            if not sockets:
                return 0
            sockets.discard(ws)
            if not sockets:
                self._by_user.pop(user_id, None)
                return 0
            return len(sockets)

    async def push_to_user(self, user_id: str | uuid.UUID, message: dict[str, Any]) -> int:
        """Fan out ``message`` to every open socket for ``user_id``.

        Returns the number of successful sends.  Dead sockets are
        scrubbed in-place so a stuck connection cannot block the
        rest of the fan-out.
        """
        try:
            uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        except (ValueError, TypeError):
            return 0

        async with self._lock:
            sockets = list(self._by_user.get(uid, ()))

        if not sockets:
            return 0

        sent = 0
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_json(message)
                sent += 1
            except Exception:  # noqa: BLE001
                dead.append(ws)

        if dead:
            async with self._lock:
                live = self._by_user.get(uid)
                if live:
                    for ws in dead:
                        live.discard(ws)
                    if not live:
                        self._by_user.pop(uid, None)
        return sent

    def subscriber_count(self, user_id: uuid.UUID) -> int:
        sockets = self._by_user.get(user_id)
        return 0 if sockets is None else len(sockets)

    def reset(self) -> None:
        """Drop every subscriber.  Used by test teardown."""
        self._by_user.clear()


# Module-level singleton (one per worker process).
notifications_ws_hub = NotificationsWsHub()
