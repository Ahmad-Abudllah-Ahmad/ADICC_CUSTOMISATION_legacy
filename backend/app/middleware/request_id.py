# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Request correlation ID middleware.

Injects a stable, per-request ID into a ``contextvars.ContextVar`` so any
log record produced anywhere in the call stack can be tagged with it via
a ``logging.Filter``. Also echoes the value back to the client as the
``X-Request-ID`` response header for trace correlation across services.

A client may supply its own ``X-Request-ID`` header (up to 64 chars,
alphanumeric + dash/underscore); otherwise a fresh 16-hex-char ``uuid4``
slice is generated.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Public contextvar - log filters read this. Default ``None`` so off-request
# log lines (boot, background tasks) render as "-" rather than a stale ID.
_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Strict allowlist for client-supplied IDs: alphanumeric, dash, underscore.
# Anything else (newlines, whitespace, control chars, header-smuggling
# attempts) is rejected and we mint a fresh ID instead.
_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def get_request_id() -> str | None:
    """Return the current request's correlation ID, if one is set."""
    return _request_id_var.get()


def _new_request_id() -> str:
    """Generate a compact 16-char hex ID - short enough for log columns."""
    return uuid.uuid4().hex[:16]


def _sanitize_client_id(value: str | None) -> str | None:
    """Accept a client-supplied ID iff it matches our strict allowlist."""
    if not value:
        return None
    value = value.strip()
    if _CLIENT_ID_RE.fullmatch(value):
        return value
    return None


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Tag every HTTP request with a correlation ID.

    * Reads ``X-Request-ID`` from the incoming request when valid; otherwise
      mints a fresh one.
    * Stores it in a module-level ``ContextVar`` for logging filters.
    * Echoes it back via ``X-Request-ID`` on the response so clients (and
      upstream proxies) can stitch logs to user-visible errors.
    """

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001, ANN201
        client_id = _sanitize_client_id(request.headers.get("X-Request-ID"))
        request_id = client_id or _new_request_id()

        token = _request_id_var.set(request_id)
        try:
            response: Response = await call_next(request)
        finally:
            _request_id_var.reset(token)

        response.headers["X-Request-ID"] = request_id
        return response


class RequestIDLogFilter:
    """Inject ``record.request_id`` so formatters can render ``%(request_id)s``.

    Implemented as a plain class (not ``logging.Filter`` subclass) so the
    standard ``addFilter`` duck-typing works without importing the logging
    module's class hierarchy at definition time.
    """

    def filter(self, record) -> bool:  # noqa: ANN001 - logging.LogRecord
        record.request_id = get_request_id() or "-"
        return True
