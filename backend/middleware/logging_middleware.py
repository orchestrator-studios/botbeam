import time
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from config.settings import settings
from config.logging_config import get_request_id

logger = logging.getLogger("botbeam.request")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Per-request logging with a request id, timing, and status-based levels.
    Mirrors the kh / table-that LoggingMiddleware (trimmed body logging)."""

    def __init__(self, app: ASGIApp, request_id_filter=None):
        super().__init__(app)
        self.request_id_filter = request_id_filter

    async def dispatch(self, request: Request, call_next):
        request_id = get_request_id()
        if self.request_id_filter:
            self.request_id_filter.request_id = request_id
        request.state.request_id = request_id

        start = time.time()
        try:
            response = await call_next(request)
            duration_ms = (time.time() - start) * 1000
            self._log_response(request, response.status_code, duration_ms)
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as exc:
            duration_ms = (time.time() - start) * 1000
            logger.exception(
                "Unhandled exception: %s %s (%.1fms): %s",
                request.method, request.url.path, duration_ms, exc,
            )
            raise
        finally:
            if self.request_id_filter:
                self.request_id_filter.request_id = None

    def _log_response(self, request: Request, status_code: int, duration_ms: float):
        line = f"{request.method} {request.url.path} {status_code} {duration_ms:.1f}ms"
        if status_code >= 500:
            logger.error(line)
        elif status_code >= 400:
            logger.warning(line)
        elif duration_ms > settings.LOG_PERFORMANCE_THRESHOLD_MS:
            logger.warning("SLOW %s", line)
        else:
            logger.info(line)
