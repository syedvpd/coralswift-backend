from pathlib import Path
from typing import Any

import httpx
import pytest

from app.integrations.email import (
    BrevoEmailSender,
    ConsoleEmailSender,
    EmailDeliveryError,
    EmailMessage,
)
from app.integrations.storage import LocalStorage, S3Storage, StorageError
from app.modules.documents.files import detect_kind, sanitize_filename
from tests import factories

MSG = EmailMessage(to="a@b.example", subject="s", html="<p>h</p>", text="t")


def brevo(handler: Any) -> BrevoEmailSender:
    return BrevoEmailSender(
        "SECRET-API-KEY",
        "noreply@x.example",
        "Coral",
        httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_brevo_success_uses_api_key_header_and_payload() -> None:
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["key"] = req.headers["api-key"]
        seen["body"] = req.content.decode()
        return httpx.Response(201, json={"messageId": "<abc@brevo>"})

    result = brevo(handler).send(MSG)
    assert result.delivered and result.provider_reference == "<abc@brevo>"
    assert (
        seen["key"] == "SECRET-API-KEY"
        and "htmlContent" in seen["body"]
        and "textContent" in seen["body"]
    )


def test_brevo_errors_never_leak_key() -> None:
    with pytest.raises(EmailDeliveryError) as e1:
        brevo(lambda r: httpx.Response(401, json={"message": "bad key"})).send(MSG)
    assert "401" in str(e1.value) and "SECRET-API-KEY" not in str(e1.value)

    def down(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    with pytest.raises(EmailDeliveryError):
        brevo(down).send(MSG)


def test_console_backend_reports_not_delivered() -> None:
    assert ConsoleEmailSender().send(MSG).delivered is False


def test_local_storage_private_and_safe(tmp_path: Path) -> None:
    s = LocalStorage(tmp_path / "root")
    s.put("enquiries/2026/11/a.pdf", b"x", "application/pdf")
    assert s.exists("enquiries/2026/11/a.pdf")
    s.delete("enquiries/2026/11/a.pdf")
    assert not s.exists("enquiries/2026/11/a.pdf")
    for bad in ("../evil.pdf", "/etc/passwd", "a/../../b", "..\\x", "a b.pdf"):
        with pytest.raises(StorageError):
            s.put(bad, b"x", "application/pdf")


def test_s3_storage_routes_partner_keys_and_wraps_errors() -> None:
    calls: list[tuple[str, str]] = []

    class Client:
        def put_object(self, **kw: Any) -> None:
            calls.append((kw["Bucket"], kw["Key"]))
            assert "ServerSideEncryption" not in kw and "ACL" not in kw

        def delete_object(self, **kw: Any) -> None:
            raise RuntimeError("secret stuff")

    s3 = S3Storage(Client(), "general", "partner-bucket")
    s3.put("partners/2026/11/a.pdf", b"x", "application/pdf")
    s3.put("enquiries/2026/11/b.pdf", b"x", "application/pdf")
    assert calls == [
        ("partner-bucket", "partners/2026/11/a.pdf"),
        ("general", "enquiries/2026/11/b.pdf"),
    ]
    with pytest.raises(StorageError) as exc:
        s3.delete("enquiries/x.pdf")
    assert "secret stuff" not in str(exc.value)


def test_file_helpers() -> None:
    assert sanitize_filename("../../a\\b/evil\x00name.pdf") == "evilname.pdf"
    assert sanitize_filename("   ") == "file" and len(sanitize_filename("a" * 400 + ".pdf")) <= 150
    assert detect_kind(factories.PDF) == "pdf" and detect_kind(factories.docx_bytes()) == "docx"
    assert detect_kind(b"hello") is None
