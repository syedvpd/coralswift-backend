import hashlib
import re
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.documents.models import Document
from tests import factories
from tests.conftest import AppFactory
from tests.fakes import InMemoryStorage

UP = "/api/v1/documents/upload"
CONTACT = "/api/v1/enquiries/contact"


def up(client: TestClient, name: str, data: bytes, ctype: str, **form: str) -> Any:
    form = {"purpose": "project_attachment", **form}
    return client.post(UP, data=form, files={"file": (name, data, ctype)})


# ---------- documents ----------
def test_allowed_file_stored_privately_with_checksum(
    client: TestClient, db: Session, storage: InMemoryStorage
) -> None:
    r = up(client, "brief.pdf", factories.PDF, "application/pdf")
    assert r.status_code == 201
    d = r.json()["data"]
    assert d["checksum_sha256"] == hashlib.sha256(factories.PDF).hexdigest()
    assert d["upload_status"] == "quarantined" and "storage_key" not in d
    doc = db.execute(select(Document)).scalar_one()
    assert storage.objects[doc.storage_key] == factories.PDF
    assert re.match(r"^enquiries/\d{4}/\d{2}/[0-9a-f]{32}\.pdf$", doc.storage_key)
    assert doc.owner_type.value == "unattached" and doc.classification.value == "restricted"


@pytest.mark.parametrize(
    "name, data, ctype",
    [
        ("malware.exe", b"MZ" + b"0" * 50, "application/octet-stream"),  # extension
        ("fake.pdf", factories.PNG, "application/pdf"),  # content != extension
        ("brief.pdf", factories.PDF, "image/png"),  # declared type contradicts content
        ("empty.pdf", b"", "application/pdf"),
        ("x.docx", b"PK\x03\x04junk", "application/octet-stream"),  # broken zip
    ],
)
def test_rejected_files(client: TestClient, name: str, data: bytes, ctype: str) -> None:
    assert up(client, name, data, ctype).status_code in (415, 422)


def test_docx_accepted_and_oversize_rejected(client: TestClient, settings: Any) -> None:
    assert (
        up(client, "a.docx", factories.docx_bytes(), "application/octet-stream").status_code == 201
    )
    big = factories.PDF + b"0" * settings.max_upload_bytes
    r = up(client, "big.pdf", big, "application/pdf")
    assert r.status_code == 413 and r.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_duplicate_filenames_and_path_traversal(
    client: TestClient, db: Session, storage: InMemoryStorage
) -> None:
    for _ in range(2):
        assert up(client, "same.pdf", factories.PDF, "application/pdf").status_code == 201
    r = up(client, "../../etc/passwd.pdf", factories.PDF, "application/pdf")
    assert r.status_code == 201 and r.json()["data"]["original_filename"] == "passwd.pdf"
    keys = {d.storage_key for d in db.execute(select(Document)).scalars()}
    assert len(keys) == 3 and all(".." not in k and "passwd" not in k for k in keys)
    assert set(storage.objects) == keys


def test_storage_failure_marks_document_failed(
    client: TestClient, db: Session, storage: InMemoryStorage
) -> None:
    storage.fail = True
    r = up(client, "a.pdf", factories.PDF, "application/pdf")
    assert r.status_code == 503 and r.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert db.execute(select(Document.upload_status)).scalar_one().value == "failed"
    assert storage.objects == {}


def test_partner_evidence_needs_category_and_uses_partner_area(
    client: TestClient, db: Session
) -> None:
    assert (
        up(
            client, "a.pdf", factories.PDF, "application/pdf", purpose="partner_evidence"
        ).status_code
        == 422
    )
    r = up(
        client,
        "a.pdf",
        factories.PDF,
        "application/pdf",
        purpose="partner_evidence",
        category="registration_proof",
    )
    assert r.status_code == 201
    assert db.execute(select(Document.storage_key)).scalar_one().startswith("partners/")
    assert (
        up(
            client, "a.pdf", factories.PDF, "application/pdf", category="registration_proof"
        ).status_code
        == 422
    )


def test_no_public_download_route(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    doc_paths = {
        p: list(v) for p, v in paths.items() if p.startswith("/api/v1/documents")
    }  # public (Phase 1) area only
    assert doc_paths == {UP: ["post"]}
    assert client.get("/api/v1/documents/x").status_code == 404


# ---------- status lookup ----------
def _submit(client: TestClient) -> dict[str, Any]:
    return dict(client.post(CONTACT, json=factories.contact()).json()["data"])


def test_status_with_token_returns_minimal_fields(client: TestClient) -> None:
    sub = _submit(client)
    r = client.get(
        f"/api/v1/enquiries/{sub['reference_number']}/status",
        headers={"X-Lookup-Token": sub["lookup_token"]},
    )
    assert r.status_code == 200
    assert set(r.json()["data"]) == {"reference_number", "enquiry_type", "status", "submitted_at"}


def test_status_failures_are_indistinguishable(client: TestClient) -> None:
    sub = _submit(client)
    ref = sub["reference_number"]
    other = _submit(client)
    cases = [
        (ref, {"X-Lookup-Token": "0" * 40}),  # wrong token
        (ref, {}),  # no token
        (ref, {"X-Lookup-Token": other["lookup_token"]}),  # another enquiry's token
        ("CS-ENQ-2026-999999", {"X-Lookup-Token": sub["lookup_token"]}),  # unknown ref
        ("not-a-reference", {"X-Lookup-Token": sub["lookup_token"]}),
    ]
    bodies = set()
    for reference, headers in cases:
        r = client.get(f"/api/v1/enquiries/{reference}/status", headers=headers)
        assert r.status_code == 404
        bodies.add(r.text)
    assert len(bodies) == 1


# ---------- abuse protection ----------
def test_rate_limit(app_factory: AppFactory) -> None:
    with TestClient(app_factory(rate_limit_per_minute=2), raise_server_exceptions=False) as c:
        codes = [c.post(CONTACT, json=factories.contact()).status_code for _ in range(3)]
        assert codes == [201, 201, 429]
        r = c.post(CONTACT, json=factories.contact())
        assert (
            r.headers["retry-after"].isdigit() and r.json()["error"]["code"] == "TOO_MANY_REQUESTS"
        )


def test_status_lookup_is_rate_limited(app_factory: AppFactory) -> None:
    with TestClient(app_factory(rate_limit_per_minute=1), raise_server_exceptions=False) as c:
        codes = [c.get("/api/v1/enquiries/CS-ENQ-2026-000001/status").status_code for _ in range(4)]
        assert codes[:3] == [404, 404, 404] and codes[3] == 429


def test_bot_check_hook(app_factory: AppFactory) -> None:
    class Deny:
        def verify(self, token: str | None, client_ip: str) -> bool:
            return token == "human"

    with TestClient(app_factory(bot_verifier=Deny()), raise_server_exceptions=False) as c:
        r = c.post(CONTACT, json=factories.contact())
        assert r.status_code == 403 and r.json()["error"]["code"] == "BOT_CHECK_FAILED"
        ok = c.post(CONTACT, json=factories.contact(), headers={"X-Bot-Token": "human"})
        assert ok.status_code == 201


def test_oversized_request_rejected(app_factory: AppFactory) -> None:
    app: FastAPI = app_factory(max_request_body_bytes=500)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post(CONTACT, json=factories.contact(message="x" * 2000))
        assert r.status_code == 413 and r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
