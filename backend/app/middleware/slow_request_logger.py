# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Middleware to log slow API requests.

Logs a warning for any request that exceeds a configurable threshold
(default 500ms). Useful for identifying performance bottlenecks without
external APM tooling.
"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("slow_requests")

# Default threshold in seconds (500ms)
_DEFAULT_THRESHOLD_SECONDS = 0.5


class SlowRequestLoggerMiddleware(BaseHTTPMiddleware):
    """Log requests that exceed a duration threshold.

    Args:
        app: The ASGI application.
        threshold_seconds: Minimum duration (in seconds) to trigger a log
            warning. Defaults to 0.5 (500ms).
    """

    def __init__(self, app, threshold_seconds: float = _DEFAULT_THRESHOLD_SECONDS) -> None:  # noqa: ANN001
        super().__init__(app)
        self.threshold_seconds = threshold_seconds

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        start = time.monotonic()
        response: Response = await call_next(request)
        duration = time.monotonic() - start

        if duration > self.threshold_seconds:
            logger.warning(
                "Slow request: %s %s took %.2fs (status %s)",
                request.method,
                request.url.path,
                duration,
                response.status_code,
            )

        # Always add timing header for developer convenience
        response.headers["X-Response-Time"] = f"{duration:.3f}s"
        return response
