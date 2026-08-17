"""
Structured logging (spec §56).

Concurrent searches are impossible to debug from prose logs, so every record is
one JSON object and `search_id` / `job_id` ride along in context variables:
bind them once at the top of a pipeline step and every log line inside inherits
them.
"""

import json
import logging
import sys
from contextvars import ContextVar
from typing import Any

_search_id: ContextVar[str | None] = ContextVar("search_id", default=None)
_job_id: ContextVar[str | None] = ContextVar("job_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)

RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in (
            ("search_id", _search_id.get()),
            ("job_id", _job_id.get()),
            ("user_id", _user_id.get()),
        ):
            if value:
                payload[key] = value

        # Anything passed as logger.info("event", extra={...}) is a field.
        payload.update({k: v for k, v in record.__dict__.items() if k not in RESERVED})

        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # uvicorn's own handlers would double-print every line.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


def bind(
    search_id: str | None = None,
    job_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Attach identifiers to every log record emitted from here on."""
    if search_id is not None:
        _search_id.set(search_id)
    if job_id is not None:
        _job_id.set(job_id)
    if user_id is not None:
        _user_id.set(user_id)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
