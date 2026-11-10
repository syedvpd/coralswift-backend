"""PRD Phase 1 gap closure: SEO/media metadata on public content, privacy-request email proof."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from app.modules.engagement.models import PrivacyRequest
from tests.fakes import RecordingEmail
from tests.helpers import bearer, last_token, login, make_staff

AC = "/api/v1/admin/content"
SEO = {
    "seo_title": "Services | Coral Swift",
    "seo_description": "IT and business operations services.",
    "canonical_url": "https://coralswift.example/services",
    "og_title": "Coral Swift services",
    "og_description": "What we do",
    "og_image_url": "https://cdn.example/og.png",
    "image_url": "https://cdn.example/hero.jpg",
    "image_alt": "Team at work",
}


def _h(client: TestClient, db: Session, settings: Settings, role: StaffRole) -> dict[str, str]:
    return bearer(login(client, make_staff(db, settings, role).email)["access_token"])


def test_seo_and_media_fields_flow_to_the_public_site_only_when_published(
    client: TestClient, db: Session, settings: Settings
) -> None:
    ca = _h(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    body = {"slug": "services", "content_type": "page", "title": "Services", "body": "Text", **SEO}
    made = client.post(AC, headers=ca, json=body)
    assert made.status_code == 201, made.text
    item = made.json()["data"]
    assert all(item[k] == v for k, v in SEO.items())
    assert client.get("/api/v1/content/services").status_code == 404  # draft is never public

    client.post(f"{AC}/{item['id']}/submit", headers=ca, json={})
    client.post(f"{AC}/{item['id']}/approve", headers=sa, json={"note": "ok"})
    assert client.post(f"{AC}/{item['id']}/publish", headers=ca, json={}).status_code == 200
    public = client.get("/api/v1/content/services").json()["data"]
    assert all(public[k] == v for k, v in SEO.items())
    listed = client.get("/api/v1/content").json()["data"]
    assert listed[0]["canonical_url"] == SEO["canonical_url"]
    assert "owner_id" not in public and "review_note" not in public  # no internal fields


def test_seo_urls_must_be_https_and_null_clears_only_seo_fields(
    client: TestClient, db: Session, settings: Settings
) -> None:
    ca = _h(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    base = {"slug": "about", "content_type": "page", "title": "About", "body": "Text"}
    for bad in ("http://insecure.example", "javascript:alert(1)", "https://a b.example"):
        r = client.post(AC, headers=ca, json={**base, "canonical_url": bad})
        assert r.status_code == 422, bad
    assert client.post(AC, headers=ca, json={**base, "seo_title": "x" * 201}).status_code == 422
    item = client.post(AC, headers=ca, json={**base, **SEO}).json()["data"]
    cleared = client.patch(f"{AC}/{item['id']}", headers=ca, json={"canonical_url": None})
    assert cleared.status_code == 200 and cleared.json()["data"]["canonical_url"] is None
    assert cleared.json()["data"]["seo_title"] == SEO["seo_title"]  # untouched fields stay
    keep = client.patch(f"{AC}/{item['id']}", headers=ca, json={"title": None})
    assert keep.json()["data"]["title"] == "About"  # null never clears a required field
    assert (
        client.patch(f"{AC}/{item['id']}", headers=ca, json={"og_image_url": "ftp://x"}).status_code
        == 422
    )


def test_privacy_request_needs_email_confirmation_before_staff_can_act(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa = _h(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    url = "/api/v1/privacy/requests"
    made = client.post(url, json={"email": "who@example.com", "kind": "access"})
    assert made.status_code == 201 and set(made.json()["data"]) == {"reference"}
    row = client.get("/api/v1/admin/privacy-requests", headers=sa).json()["data"][0]
    assert row["email_verified"] is False and "token" not in str(row).lower()
    for action in ("in_progress", "completed"):
        r = client.post(
            f"/api/v1/admin/privacy-requests/{row['id']}", headers=sa, json={"status": action}
        )
        assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"
    assert (
        client.post(f"/api/v1/admin/privacy-requests/{row['id']}/execute", headers=sa).status_code
        == 409
    )
    rejected = client.post(
        f"/api/v1/admin/privacy-requests/{row['id']}",
        headers=sa,
        json={"status": "rejected", "resolution_note": "spam"},
    )
    assert rejected.status_code == 200  # an unconfirmed request can be rejected

    verify = f"{url}/verify"
    assert client.post(verify, json={"token": "cs_" + "x" * 40}).status_code == 400
    assert client.post(verify, json={"token": "short"}).status_code == 422
    token = last_token(email, "who@example.com")
    ok = client.post(verify, json={"token": token})
    assert ok.status_code == 200
    assert (
        client.get("/api/v1/admin/privacy-requests", headers=sa).json()["data"][0]["email_verified"]
        is True
    )
    assert client.post(verify, json={"token": token}).status_code == 400  # single use


def test_expired_privacy_link_is_refused(
    client: TestClient, db: Session, settings: Settings, email: RecordingEmail
) -> None:
    client.post(
        "/api/v1/privacy/requests", json={"email": "late@example.com", "kind": "correction"}
    )
    token = last_token(email, "late@example.com")
    db.execute(
        update(PrivacyRequest).values(verification_expires_at=utcnow() - timedelta(minutes=1))
    )
    db.commit()
    r = client.post("/api/v1/privacy/requests/verify", json={"token": token})
    assert r.status_code == 400 and r.json()["error"]["code"] == "TOKEN_EXPIRED"
