import json
import logging

import pytest

from app.common.pagination import PageParams, page_meta
from app.core.logging import JsonFormatter, redact_text
from app.core.security import constant_time_equals, generate_token


@pytest.mark.parametrize(
    "raw, secret",
    [
        ("login password=hunter2 ok", "hunter2"),
        ("Authorization: Bearer abc.def-123", "abc.def-123"),
        ("connect postgresql://user:s3cr3t@db:5432/x failed", "s3cr3t"),
        ('{"token": "tok_999"}', "tok_999"),
    ],
)
def test_redact_text(raw: str, secret: str) -> None:
    out = redact_text(raw)
    assert secret not in out and "[REDACTED]" in out


def test_json_formatter_redacts_extras_and_exceptions() -> None:
    try:
        raise RuntimeError("boom password=pw123")
    except RuntimeError:
        import sys

        record = logging.LogRecord("t", logging.ERROR, "f", 1, "msg", (), sys.exc_info())
    record.secret_key = "abc"
    record.path = "/x"
    data = json.loads(JsonFormatter().format(record))
    assert data["secret_key"] == "[REDACTED]"
    assert data["path"] == "/x"
    assert "pw123" not in data["exception"]


def test_generate_token_unique_and_compare() -> None:
    a, b = generate_token(), generate_token()
    assert a != b and len(a) >= 32
    assert constant_time_equals(a, a) and not constant_time_equals(a, b)


def test_pagination_math() -> None:
    p = PageParams(page=3, page_size=20)
    assert p.offset == 40
    assert page_meta(p, 41) == {"page": 3, "page_size": 20, "total": 41, "pages": 3}
    assert page_meta(p, 0)["pages"] == 0
