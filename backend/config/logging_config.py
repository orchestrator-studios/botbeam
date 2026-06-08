import logging
import logging.handlers
import os
import uuid

from config.settings import settings


class RequestIdFilter(logging.Filter):
    """Adds the current request_id to every log record."""
    def __init__(self, name=""):
        super().__init__(name)
        self.request_id = None

    def filter(self, record):
        if not getattr(record, "request_id", None):
            record.request_id = self.request_id or "-"
        return True


def get_request_id() -> str:
    return uuid.uuid4().hex[:8]


_request_id_filter = RequestIdFilter()


def setup_logging():
    """Configure root logging: console + a daily-rotating file in LOG_DIR.

    Mirrors the kh / table-that setup (formatter with [request_id], TimedRotatingFileHandler).
    Returns (logger, request_id_filter) for the LoggingMiddleware.
    """
    os.makedirs(settings.LOG_DIR, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(request_id)s] - %(name)s - %(message)s"
    )

    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(_request_id_filter)
    root.addHandler(console)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        os.path.join(settings.LOG_DIR, f"{settings.LOG_FILENAME_PREFIX}.log"),
        when="midnight",
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(_request_id_filter)
    root.addHandler(file_handler)

    # Uvicorn's own access log duplicates ours — quiet it.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    return logging.getLogger("botbeam"), _request_id_filter
