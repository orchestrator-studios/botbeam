import time
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from config.settings import settings
from config.logging_config import get_request_id, request_id_var

logger = logging.getLogger("botbeam.request")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Per-request logging with a request id, timing, and status-based levels.
    Mirrors the kh / table-that LoggingMiddleware (trimmed body logging)."""

    async def dispatch(self, request: Request, call_next):
        request_id = get_request_id()
        token = request_id_var.set(request_id)
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
            request_id_var.reset(token)

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
