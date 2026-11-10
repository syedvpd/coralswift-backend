import hashlib
import uuid

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.enquiries.models import Activity
from app.modules.partner_documents.models import PartnerDocument, PartnerDocumentVersion
from tests import factories
from tests.fakes import InMemoryStorage, RecordingEmail
from tests.helpers import Partner, onboard_partner

D = "/api/v1/partner/documents"


def up(
    client: TestClient,
    p: Partner,
    category: str = "registration_proof",
    data: bytes = factories.PDF,
    name: str = "reg.pdf",
    ctype: str = "application/pdf",
    **form: str,
) -> Response:
    response: Response = client.post(
        D,
        headers=p.headers,
        data={"category": category, **form},
        files={"file": (name, data, ctype)},
    )
    return response


def two(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> tuple[Partner, Partner]:
    return (
        onboard_partner(client, db, settings, email, org_name="Org A"),
        onboard_partner(client, db, settings, email, org_name="Org B"),
    )


def test_requires_login(client: TestClient) -> None:
    assert client.get(D).status_code == 401
    r = client.post(
        D, data={"category": "registration_proof"}, files={"file": ("a.pdf", factories.PDF)}
    )
    assert r.status_code == 401


def test_upload_metadata_private_storage(
    client: TestClient,
    db: Session,
    settings: Settings,
    email: RecordingEmail,
    storage: InMemoryStorage,
) -> None:
    p = onboard_partner(client, db, settings, email)
    r = up(client, p, expires_on="2030-01-31")
    assert r.status_code == 201
    cv = r.json()["data"]["current_version"]
    assert r.json()["data"]["can_replace"] is True
    assert r.json()["data"]["can_remove"] is True
    assert r.json()["data"]["can_download"] is True
    assert cv["checksum_sha256"] == hashlib.sha256(factories.PDF).hexdigest()
    assert cv["upload_status"] == "quarantined" and cv["review_status"] == "pending"
    assert cv["expires_on"] == "2030-01-31" and "storage_key" not in r.text
    version = db.execute(select(PartnerDocumentVersion)).scalar_one()
    assert (
        version.storage_key.startswith("partners/portal/")
        and p.organization_id not in version.storage_key
    )
    assert storage.objects[version.storage_key] == factories.PDF


def test_rejected_uploads(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    assert (
        up(
            client, p, name="x.exe", data=b"MZ" + b"0" * 40, ctype="application/octet-stream"
        ).status_code
        == 415
    )
    assert up(client, p, data=factories.PNG, name="fake.pdf").status_code == 415
    assert up(client, p, category="not_a_category").status_code == 422
    assert (
        up(client, p, name="../../etc/passwd.pdf").json()["data"] is not None
    )  # traversal name is harmless
    big = factories.PDF + b"0" * settings.max_upload_bytes
    assert up(client, p, data=big).status_code == 413


def test_storage_failure(
    client: TestClient,
    db: Session,
    settings: Settings,
    email: RecordingEmail,
    storage: InMemoryStorage,
) -> None:
    p = onboard_partner(client, db, settings, email)
    storage.fail = True
    r = up(client, p)
    assert r.status_code == 503
    assert db.execute(select(PartnerDocumentVersion.upload_status)).scalar_one().value == "failed"
    storage.fail = False
    # the failed upload never became current, so the document has no usable version yet
    assert client.get(D, headers=p.headers).json()["data"][0]["current_version"] is None


def test_replace_keeps_history_and_download_audited(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    p = onboard_partner(client, db, settings, email)
    doc_id = up(client, p).json()["data"]["id"]
    second = client.post(
        f"{D}/{doc_id}/versions",
        headers=p.headers,
        files={"file": ("v2.docx", factories.docx_bytes(), "application/octet-stream")},
    )
    assert second.status_code == 201 and second.json()["data"]["current_version"]["version_no"] == 2
    hist = client.get(f"{D}/{doc_id}/history", headers=p.headers).json()["data"]
    assert [h["version_no"] for h in hist] == [2, 1]
    old = client.get(f"{D}/{doc_id}/download?version=1", headers=p.headers)
    assert old.status_code == 200 and old.content == factories.PDF
    assert (
        old.headers["content-type"] == "application/pdf"
        and old.headers["cache-control"] == "private, no-store"
    )
    assert client.get(f"{D}/{doc_id}/download", headers=p.headers).content == factories.docx_bytes()
    actions = list(db.execute(select(Activity.action)).scalars())
    assert actions.count("document.downloaded") == 2 and "document.replaced" in actions
    assert client.get(f"{D}/{doc_id}/download?version=9", headers=p.headers).status_code == 404


def test_cross_organization_access_is_404(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    a, b = two(client, db, settings, email)
    doc_id = up(client, a).json()["data"]["id"]
    for method, url in (
        ("get", f"{D}/{doc_id}"),
        ("get", f"{D}/{doc_id}/download"),
        ("get", f"{D}/{doc_id}/history"),
        ("delete", f"{D}/{doc_id}"),
    ):
        r = client.request(method, url, headers=b.headers)
        assert r.status_code == 404, (method, url)
    r = client.post(
        f"{D}/{doc_id}/versions", headers=b.headers, files={"file": ("n.pdf", factories.PDF)}
    )
    assert r.status_code == 404
    assert client.get(D, headers=b.headers).json()["data"] == []
    assert (
        client.get(f"{D}/{uuid.uuid4()}", headers=b.headers).status_code == 404
    )  # same as foreign id
    # nothing changed for A
    assert len(client.get(f"{D}/{doc_id}/history", headers=a.headers).json()["data"]) == 1


def test_soft_remove_retains_data(
    client: TestClient,
    db: Session,
    settings: Settings,
    email: RecordingEmail,
    storage: InMemoryStorage,
) -> None:
    p = onboard_partner(client, db, settings, email)
    doc_id = up(client, p).json()["data"]["id"]
    assert client.delete(f"{D}/{doc_id}", headers=p.headers).status_code == 200
    assert client.get(f"{D}/{doc_id}", headers=p.headers).status_code == 404
    assert client.get(D, headers=p.headers).json()["data"] == []
    row = db.execute(select(PartnerDocument)).scalar_one()
    assert row.status.value == "removed" and row.removed_at is not None
    assert len(storage.objects) == 1  # bytes retained (no retention policy approved)
