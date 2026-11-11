"""Structured JSON logging with request correlation and secret redaction."""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
client_ip_var: ContextVar[str | None] = ContextVar("client_ip", default=None)
user_agent_var: ContextVar[str | None] = ContextVar("user_agent", default=None)

_SENSITIVE_KEY = re.compile(
    r"password|passwd|token|secret|authorization|api[_-]?key|cookie|database_url", re.I
)
_KV_PATTERN = re.compile(
    r"(?i)(password|passwd|token|secret|authorization|api[_-]?key|cookie)(\"?\s*[=:]\s*\"?)([^\s\",;&]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)[\w\-.~+/]+=*")
_URL_CREDS_PATTERN = re.compile(r"(://[^:/\s@]+:)[^@\s]+@")
_STANDARD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


def redact_text(text: str) -> str:
    text = _URL_CREDS_PATTERN.sub(r"\1[REDACTED]@", text)
    text = _BEARER_PATTERN.sub(r"\1[REDACTED]", text)
    return _KV_PATTERN.sub(r"\1\2[REDACTED]", text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
            "request_id": getattr(record, "request_id", None) or request_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRS or key == "request_id":
                continue
            if _SENSITIVE_KEY.search(key):
                payload[key] = "[REDACTED]"
            else:
                payload[key] = redact_text(value) if isinstance(value, str) else value
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Uvicorn's own handlers would emit non-JSON lines; our middleware logs requests instead.
    for name in ("uvicorn", "uvicorn.error"):
        uv = logging.getLogger(name)
        uv.handlers.clear()
        uv.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
