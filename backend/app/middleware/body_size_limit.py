# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Global request-body-size backstop middleware.

A coarse safety net that complements the per-endpoint upload caps. It stops an
absurdly large request body from ever reaching an endpoint that might read it
unbounded (``await request.body()`` / ``request.json()``) and OOM the single
worker on a small VPS. Enforced two ways:

  * a fast reject on a declared ``Content-Length`` that already exceeds the
    ceiling, before a single body byte is read;
  * a streaming byte count for chunked bodies with no ``Content-Length``, which
    aborts with ``413`` the moment the running total crosses the ceiling - as
    long as the endpoint has not already started sending its response.

The ceiling is deliberately high - above every built-in per-endpoint cap - so
it never interferes with a legitimate large upload; the per-endpoint guards stay
the fine-grained defense. This is a backstop, not a replacement for them.

Implemented as a plain ASGI middleware (not ``BaseHTTPMiddleware``) so it can
inspect and short-circuit the body stream without buffering it into memory - the
very thing we are protecting against.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _BodyTooLarge(Exception):
    """Internal signal that the streamed request body exceeded the ceiling."""


def _declared_content_length(scope: Scope) -> int | None:
    """Return the request's declared ``Content-Length``, or ``None``.

    Args:
        scope: The ASGI HTTP connection scope.

    Returns:
        The parsed non-negative content length, or ``None`` when the header is
        absent or unparseable.
    """
    for key, value in scope.get("headers", []):
        if key == b"content-length":
            try:
                length = int(value.decode("latin-1").strip())
            except ValueError:
                return None
            return length if length >= 0 else None
    return None


class MaxBodySizeMiddleware:
    """Reject requests whose body exceeds a generous global ceiling.

    Args:
        app: The wrapped ASGI application.
        max_body_bytes: The ceiling in bytes. ``0`` (or negative) disables the
            check entirely and passes every request straight through.
    """

    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.max_body_bytes <= 0:
            await self.app(scope, receive, send)
            return

        declared = _declared_content_length(scope)
        if declared is not None and declared > self.max_body_bytes:
            await self._send_413(send)
            return

        total = 0
        response_started = False

        async def counting_receive() -> Message:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_body_bytes:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLarge:
            # Only safe to inject a 413 if the endpoint has not begun its own
            # response. If it has, the oversized body is already being drained;
            # dropping it (and the connection) is the best we can do.
            if not response_started:
                await self._send_413(send)

    @staticmethod
    async def _send_413(send: Send) -> None:
        body = b'{"detail":"Request body too large"}'
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
