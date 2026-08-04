"""Centralized logging configuration for the SHL backend.

Usage:
    from src.shl.logging_config import setup_logging
    setup_logging()

Environment variables:
    SHL_LOG_LEVEL   Log level (DEBUG, INFO, WARNING, ERROR). Default: INFO.
    SHL_LOG_FORMAT  "json" for structured JSON output, "text" for human-readable. Default: json.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Structured JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Human-readable log formatter for development."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )


def setup_logging() -> None:
    """Configure root logger based on environment variables.

    Call once at application startup (CLI entrypoint).
    """
    level_name = os.environ.get("SHL_LOG_LEVEL", "INFO").upper()
    log_format = os.environ.get("SHL_LOG_FORMAT", "json").lower()

    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Remove any existing handlers (avoid duplicates on re-init).
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    if log_format == "text":
        handler.setFormatter(TextFormatter())
    else:
        handler.setFormatter(JsonFormatter())

    root.addHandler(handler)

    # Quiet noisy third-party loggers.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
