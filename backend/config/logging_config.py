import json
import logging
import logging.handlers
import os
import uuid
from contextvars import ContextVar

from config.settings import settings

# Set per request by LoggingMiddleware. A ContextVar (not a mutable attribute on
# the filter) so concurrent requests can't cross-tag each other's log lines.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Adds the current request_id to every log record."""

    def filter(self, record):
        if not getattr(record, "request_id", None):
            record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Structured file logs (LOG_FORMAT=json) — mirrors the kh / table-that formatter."""

    def format(self, record):
        entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def get_request_id() -> str:
    return uuid.uuid4().hex[:8]


def setup_logging() -> logging.Logger:
    """Configure root logging: console + a daily-rotating file in LOG_DIR.

    Mirrors the kh / table-that setup (formatter with [request_id],
    TimedRotatingFileHandler, optional JSON file format).
    """
    os.makedirs(settings.LOG_DIR, exist_ok=True)

    standard_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(request_id)s] - %(name)s - %(message)s"
    )
    request_id_filter = RequestIdFilter()

    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(standard_formatter)
    console.addFilter(request_id_filter)
    root.addHandler(console)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        os.path.join(settings.LOG_DIR, f"{settings.LOG_FILENAME_PREFIX}.log"),
        when="midnight",
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        JsonFormatter() if settings.LOG_FORMAT == "json" else standard_formatter
    )
    file_handler.addFilter(request_id_filter)
    root.addHandler(file_handler)

    # Uvicorn's own access log duplicates ours — quiet it.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # watchfiles logs every filesystem change ("N changes detected") — noisy. Quiet it.
    logging.getLogger("watchfiles.main").setLevel(logging.WARNING)

    return logging.getLogger("botbeam")
